"""Defines the zone sensors for amt-8000."""
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import DOMAIN
from .coordinator import AmtCoordinator
from .isec2.client import Client as ISecClient

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the zone sensors for amt-8000."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    
    # Create or reuse coordinator
    coordinator_key = f"{DOMAIN}_coordinator_{config_entry.entry_id}"
    if coordinator_key not in hass.data:
        LOGGER.info("Creating new coordinator for zone sensors")
        isec_client = ISecClient(data["host"], data["port"])
        coordinator = AmtCoordinator(hass, isec_client, data["password"])
        await coordinator.async_config_entry_first_refresh()
        hass.data[coordinator_key] = coordinator
    else:
        LOGGER.info("Reusing existing coordinator for zone sensors")
        coordinator = hass.data[coordinator_key]
    
    LOGGER.info('setting up 61 zone sensors (zones 1-61)...')
    
    # Create 61 zone entities (1-61)
    zones = []
    for zone in range(1, 62):
        zones.append(AmtZoneSensor(coordinator, zone))
    
    async_add_entities(zones)


class AmtZoneSensor(CoordinatorEntity, SensorEntity):
    """Define a Amt Zone Sensor."""

    def __init__(self, coordinator, zone_number):
        """Initialize the zone sensor."""
        super().__init__(coordinator)
        self.zone_number = zone_number
        self.status = None
        self._attr_device_class = "motion"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the stored value on coordinator updates."""
        self.status = self.coordinator.data
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"AMT-8000 Zone {self.zone_number}"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"amt8000.zone_{self.zone_number}"

    @property
    def state(self) -> str:
        """Return the state of the zone."""
        if self.status is None:
            return "unknown"
        
        # Get zone state from coordinator data
        zones = self.status.get("zones", {})
        zone_data = zones.get(self.zone_number, {})
        
        # A zone is considered "open" if it's either open or violated
        if zone_data.get("open", False) or zone_data.get("violated", False):
            return "open"
        else:
            return "closed"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self.status is None:
            return False
        
        zones = self.status.get("zones", {})
        zone_data = zones.get(self.zone_number, {})
        
        # For debugging - temporarily make zones 1-20 available by default
        # Later we can use the actual enabled status
        if self.zone_number <= 20:
            available = True  # Always available for first 20 zones
        else:
            available = zone_data.get("enabled", False)
        
        return available

    @property
    def icon(self) -> str:
        """Return the icon for the zone."""
        if self.state == "open":
            return "mdi:motion-sensor"
        return "mdi:motion-sensor-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.status is None:
            return {"zone_number": self.zone_number}
        
        zones = self.status.get("zones", {})
        zone_data = zones.get(self.zone_number, {})
        
        return {
            "zone_number": self.zone_number,
            "enabled": zone_data.get("enabled", False),
            "open": zone_data.get("open", False),
            "violated": zone_data.get("violated", False),
            "bypassed": zone_data.get("anulated", False),
            "tamper": zone_data.get("tamper", False),
            "low_battery": zone_data.get("lowBattery", False),
        }
