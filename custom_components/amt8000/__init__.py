"""The AMT-8000 integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback

from .const import DOMAIN

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["alarm_control_panel", "sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AMT-8000 from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Set up options listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    LOGGER.info("Configuration options updated, reloading entry...")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    LOGGER.info(f"Starting unload process for entry {entry.entry_id}")
    
    # Force cleanup of coordinator before unloading platforms
    coordinator_key = f"{DOMAIN}_coordinator_{entry.entry_id}"
    if coordinator_key in hass.data:
        coordinator = hass.data[coordinator_key]
        LOGGER.info("Performing coordinator cleanup...")
        try:
            await coordinator.async_cleanup()
        except Exception as e:
            LOGGER.error(f"Error during coordinator cleanup: {e}")
        
        # Remove coordinator from hass.data
        hass.data.pop(coordinator_key, None)
        LOGGER.info("Coordinator removed from hass.data")

    # Unload all platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Remove entry data only after successful unload
        hass.data[DOMAIN].pop(entry.entry_id, None)
        LOGGER.info(f"Successfully unloaded entry {entry.entry_id}")
    else:
        LOGGER.error(f"Failed to unload platforms for entry {entry.entry_id}")

    return unload_ok
