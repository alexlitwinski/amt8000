"""The AMT-8000 integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback

from .const import DOMAIN
from .coordinator import AmtCoordinator
from .isec2.client import Client as ISecClient

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["alarm_control_panel", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AMT-8000 from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    
    # Create shared coordinator
    data = entry.data
    isec_client = ISecClient(data["host"], data["port"])
    coordinator = AmtCoordinator(hass, isec_client, data["password"])
    
    # Perform first refresh
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator in hass.data
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "config": data
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
