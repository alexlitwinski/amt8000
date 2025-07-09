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

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the zone sensors for amt-8000."""
    LOGGER.debug(f"=== SENSOR SETUP START ===")
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
        
        LOGGER.info('Setting up 61 zone sensors (zones 1-61)...')
        
        # Create 61 zone entities (1-61)
        zones = []
        for zone in range(1, 62):
            LOGGER.debug(f"Creating zone sensor {zone}")
            zones.append(AmtZoneSensor(coordinator, zone))
        
        LOGGER.debug(f"Created {len(zones)} zone sensors")
        LOGGER.debug("Calling async_add_entities...")
        
        async_add_entities(zones)
        
        LOGGER.info(f"Successfully added {len(zones)} zone sensors!")
        LOGGER.debug(f"=== SENSOR SETUP END ===")
        
    except Exception as e:
        LOGGER.error(f"ERRO NO SETUP DE SENSORS: {e}")
        LOGGER.exception("Stack trace completo:")
        raise


class AmtZoneSensor(CoordinatorEntity, SensorEntity):
    """Define a Amt Zone Sensor."""

    def __init__(self, coordinator, zone_number):
        """Initialize the zone sensor."""
        LOGGER.debug(f"Initializing zone sensor {zone_number}")
        super().__init__(coordinator)
        self.zone_number = zone_number
        self.status = None
        self._attr_device_class = "motion"
        LOGGER.debug(f"Zone sensor {zone_number} initialized")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the stored value on coordinator updates."""
        self.status = self.coordinator.data
        
        # Simple debug logging for first few zones only
        if self.status and "zones" in self.status and self.zone_number <= 5:
            zones = self.status["zones"]
            if self.zone_number in zones:
                zone_data = zones[self.zone_number]
                if not hasattr(self, '_last_state'):
                    self._last_state = None
                
                current_open = zone_data.get('open', False) or zone_data.get('violated', False)
                if self._last_state != current_open:
                    LOGGER.info(f"Zone {self.zone_number} state changed: {self._last_state} → {current_open}")
                    self._last_state = current_open
        
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
        return self.coordinator.last_update_success and self.status is not None

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
