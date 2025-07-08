"""Defines the binary sensors for amt-8000."""
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
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
    """Set up the binary sensors for amt-8000."""
    # Retrieve the coordinator from hass.data
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    LOGGER.info('Setting up connection failure binary sensor...')
    
    # Create connection failure binary sensor
    binary_sensors = [
        AmtConnectionFailureSensor(coordinator)
    ]
    
    async_add_entities(binary_sensors)


class AmtConnectionFailureSensor(CoordinatorEntity, BinarySensorEntity):
    """Define a connection failure binary sensor for AMT-8000."""

    def __init__(self, coordinator):
        """Initialize the connection failure sensor."""
        super().__init__(coordinator)
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the stored value on coordinator updates."""
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "AMT-8000 Falha na Conexão"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return "amt8000.connection_failure"

    @property
    def is_on(self) -> bool:
        """Return True if connection has failed."""
        return self.coordinator.connection_failed

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # This sensor should always be available to report connection status
        return True

    @property
    def icon(self) -> str:
        """Return the icon for the sensor."""
        if self.is_on:
            return "mdi:alert-circle"
        return "mdi:check-circle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "last_update_success": self.coordinator.last_update_success,
            "update_interval": str(self.coordinator.update_interval),
            "attempts": getattr(self.coordinator, 'attempt', 0),
        }
