"""Defines the zone sensors for amt-8000."""
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

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the zone sensors for amt-8000."""
    # Retrieve the coordinator from hass.data, which is now set up in __init__.py
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    LOGGER.info('Setting up 61 zone sensors (zones 1-61)...')
    
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
        self._attr_device_class = "motion"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the stored value on coordinator updates."""
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
        if self.coordinator.data is None:
            return "unknown"
        
        # Get zone state from coordinator data
        status = self.coordinator.data
        zones = status.get("zones", {})
        zone_data = zones.get(self.zone_number, {})
        
        # A zone is considered "open" if it's either open or violated
        if zone_data.get("open", False) or zone_data.get("violated", False):
            return "open"
        else:
            return "closed"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def icon(self) -> str:
        """Return the icon for the zone."""
        if self.state == "open":
            return "mdi:motion-sensor"
        return "mdi:motion-sensor-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data is None:
            return {"zone_number": self.zone_number}
        
        status = self.coordinator.data
        zones = status.get("zones", {})
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
