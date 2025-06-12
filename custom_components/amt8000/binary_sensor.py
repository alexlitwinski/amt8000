"""Defines the binary sensors for amt-8000."""
from datetime import timedelta
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
from .coordinator import AmtCoordinator
from .isec2.client import Client as ISecClient

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=4)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensors for amt-8000."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    
    # Reuse coordinator if it exists (created by alarm_control_panel or sensor)
    coordinator_key = f"{DOMAIN}_coordinator_{config_entry.entry_id}"
    if coordinator_key not in hass.data:
        LOGGER.info("Creating new coordinator for binary sensors")
        isec_client = ISecClient(data["host"], data["port"])
        coordinator = AmtCoordinator(hass, isec_client, data["password"])
        try:
            await coordinator.async_config_entry_first_refresh()
            hass.data[coordinator_key] = coordinator
        except Exception as e:
            LOGGER.error(f"Failed to initialize coordinator: {e}")
            raise
    else:
        LOGGER.info("Reusing existing coordinator for binary sensors")
        coordinator = hass.data[coordinator_key]
    
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
