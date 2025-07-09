"""The AMT-8000 integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import AmtCoordinator
from .isec2.client import Client as ISecClient, CommunicationError

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["alarm_control_panel", "sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AMT-8000 from a config entry."""
    LOGGER.debug(f"=== INIT SETUP START ===")
    LOGGER.debug(f"Entry ID: {entry.entry_id}")
    LOGGER.debug(f"Entry data: {entry.data}")
    LOGGER.debug(f"Platforms to setup: {PLATFORMS}")

    hass.data.setdefault(DOMAIN, {})
    
    # Get host, port, and password from the config entry
    host = entry.data["host"]
    port = entry.data["port"]
    password = entry.data["password"]
    
    # Get update interval from options or data, with a default
    update_interval = entry.options.get("update_interval", entry.data.get("update_interval", 4))

    LOGGER.debug(f"Host: {host}, Port: {port}, Update interval: {update_interval}")

    # Create the client and coordinator
    isec_client = ISecClient(host, port)
    coordinator = AmtCoordinator(hass, isec_client, password, update_interval)

    LOGGER.debug("Coordinator created, performing first refresh...")

    # Perform the first refresh to ensure the connection is valid
    try:
        await coordinator.async_config_entry_first_refresh()
        LOGGER.debug("First refresh successful")
    except CommunicationError as err:
        # If the first connection fails, raise ConfigEntryNotReady to let HA retry later
        LOGGER.error(f"Failed to connect to AMT-8000 at {host}:{port}: {err}")
        raise ConfigEntryNotReady(f"Failed to connect to AMT-8000 at {host}:{port}: {err}") from err

    # Store the coordinator and entry data in hass.data
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "config": entry.data,
    }

    LOGGER.debug(f"Data stored in hass.data[{DOMAIN}][{entry.entry_id}]")
    LOGGER.debug(f"hass.data[{DOMAIN}] keys after storage: {list(hass.data[DOMAIN].keys())}")

    # Set up options listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    LOGGER.debug("Starting platform setup...")

    # Forward the setup to all platforms
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        LOGGER.info(f"Successfully set up all platforms: {PLATFORMS}")
    except Exception as e:
        LOGGER.error(f"Erro durante setup das plataformas: {e}")
        LOGGER.exception("Stack trace completo:")
        raise

    LOGGER.debug(f"=== INIT SETUP END ===")
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    LOGGER.info("Configuration options updated, reloading entry...")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    LOGGER.info(f"Starting unload process for entry {entry.entry_id}")
    
    # Get the coordinator from hass.data
    coordinator = hass.data[DOMAIN].get(entry.entry_id, {}).get("coordinator")

    # Unload all platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Perform coordinator cleanup after platforms are unloaded
    if coordinator:
        LOGGER.info("Performing coordinator cleanup...")
        try:
            await coordinator.async_cleanup()
        except Exception as e:
            LOGGER.error(f"Error during coordinator cleanup: {e}")

    if unload_ok:
        # Remove entry data only after successful unload
        hass.data[DOMAIN].pop(entry.entry_id, None)
        LOGGER.info(f"Successfully unloaded entry {entry.entry_id}")
    else:
        LOGGER.error(f"Failed to unload platforms for entry {entry.entry_id}")

    return unload_ok
