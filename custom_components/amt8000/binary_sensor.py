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

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=4)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensors for amt-8000."""
    LOGGER.debug(f"=== BINARY SENSOR SETUP START ===")
    LOGGER.debug(f"Entry ID: {config_entry.entry_id}")
    LOGGER.debug(f"DOMAIN: {DOMAIN}")
    
    try:
        # Verificar se hass.data[DOMAIN] existe
        if DOMAIN not in hass.data:
            LOGGER.error(f"DOMAIN {DOMAIN} não encontrado em hass.data!")
            LOGGER.debug(f"hass.data keys: {list(hass.data.keys())}")
            return
        
        LOGGER.debug(f"hass.data[{DOMAIN}] keys: {list(hass.data[DOMAIN].keys())}")
        
        # Verificar se o entry_id existe
        if config_entry.entry_id not in hass.data[DOMAIN]:
            LOGGER.error(f"Entry ID {config_entry.entry_id} não encontrado em hass.data[{DOMAIN}]!")
            return
        
        entry_data = hass.data[DOMAIN][config_entry.entry_id]
        LOGGER.debug(f"Entry data keys: {list(entry_data.keys())}")
        
        # Verificar se coordinator existe
        if "coordinator" not in entry_data:
            LOGGER.error(f"Coordinator não encontrado em entry data!")
            return
            
        coordinator = entry_data["coordinator"]
        LOGGER.debug(f"Coordinator found: {type(coordinator)}")
        LOGGER.debug(f"Coordinator data: {coordinator.data}")
        
        LOGGER.info('Setting up connection failure binary sensor...')
        
        # Create connection failure binary sensor
        binary_sensors = [
            AmtConnectionFailureSensor(coordinator)
        ]
        
        LOGGER.debug(f"Created {len(binary_sensors)} binary sensors")
        LOGGER.debug("Calling async_add_entities...")
        
        async_add_entities(binary_sensors)
        
        LOGGER.info(f"Successfully added {len(binary_sensors)} binary sensors!")
        LOGGER.debug(f"=== BINARY SENSOR SETUP END ===")
        
    except Exception as e:
        LOGGER.error(f"ERRO NO SETUP DE BINARY SENSORS: {e}")
        LOGGER.exception("Stack trace completo:")
        raise


class AmtConnectionFailureSensor(CoordinatorEntity, BinarySensorEntity):
    """Define a connection failure binary sensor for AMT-8000."""

    def __init__(self, coordinator):
        """Initialize the connection failure sensor."""
        LOGGER.debug("Initializing connection failure sensor")
        super().__init__(coordinator)
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        LOGGER.debug("Connection failure sensor initialized")

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
