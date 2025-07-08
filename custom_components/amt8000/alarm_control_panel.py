"""Defines the alarm control panels for amt-8000."""
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState, # <- Importa o novo formato de estado
)

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)


from .const import DOMAIN
from .coordinator import AmtCoordinator


LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the entries for amt-8000."""
    # Retrieve the coordinator and config from hass.data
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = entry_data["coordinator"]
    password = entry_data["config"]["password"]
    
    LOGGER.info('Setting up 5 alarm control panels (partitions 1-5)...')
    
    # Create 5 partition entities (1-5)
    panels = []
    for partition in range(1, 6):
        panels.append(AmtAlarmPanel(coordinator, password, partition))
    
    async_add_entities(panels)


class AmtAlarmPanel(CoordinatorEntity, AlarmControlPanelEntity):
    """Define a Amt Alarm Panel for a partition."""

    _attr_supported_features = (
          AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.TRIGGER
    )

    def __init__(self, coordinator, password, partition):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.password = password
        self.partition = partition
        # O estado agora é gerenciado pela propriedade 'state'

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the stored value on coordinator updates."""
        # O self.status foi removido pois os dados vêm de self.coordinator.data
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"AMT-8000 Partition {self.partition}"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"amt8000.partition_{self.partition}"

    @property
    def state(self) -> AlarmControlPanelState | None:
        """Return the state of the entity."""
        if self.coordinator.data is None:
            return None # Retorna None para o estado ser 'unknown'

        status = self.coordinator.data

        # Check for triggered state first
        if status.get('siren', False):
            return AlarmControlPanelState.TRIGGERED

        # Get partition-specific state from coordinator data
        partitions = status.get("partitions", {})
        partition_data = partitions.get(self.partition, {})
        
        if partition_data.get("armed", False):
            if partition_data.get("stay", False):
                return AlarmControlPanelState.ARMED_HOME
            else:
                return AlarmControlPanelState.ARMED_AWAY
        else:
            return AlarmControlPanelState.DISARMED

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    def _arm_away_command(self, client):
        """Arm partition in away mode command function"""
        LOGGER.info(f"Sending ARM command to partition {self.partition}")
        result = client.arm_system(self.partition)
        LOGGER.info(f"ARM command result for partition {self.partition}: {result}")
        if result == "armed":
            return 'armed_away'
        return result

    def _disarm_command(self, client):
        """Disarm partition command function"""
        LOGGER.info(f"Sending DISARM command to partition {self.partition}")
        result = client.disarm_system(self.partition)
        LOGGER.info(f"DISARM command result for partition {self.partition}: {result}")
        if result == "disarmed":
            return 'disarmed'
        elif result == "failed":
            LOGGER.error(f"DISARM failed for partition {self.partition}")
            return "failed"
        return result

    def _trigger_alarm_command(self, client):
        """Trigger Alarm command function"""
        result = client.panic(1)
        if result == "triggered":
            return "triggered"
        return result

    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        await self.coordinator.async_execute_command(
            self._disarm_command,
            f"disarm partition {self.partition}"
        )

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        await self.coordinator.async_execute_command(
            self._arm_away_command,
            f"arm away partition {self.partition}"
        )

    async def async_alarm_trigger(self, code=None) -> None:
        """Send alarm trigger command."""
        await self.coordinator.async_execute_command(
            self._trigger_alarm_command,
            f"trigger alarm partition {self.partition}"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data is None:
            return {"partition_number": self.partition}
        
        status = self.coordinator.data
        partitions = status.get("partitions", {})
        partition_data = partitions.get(self.partition, {})
        
        return {
            "partition_number": self.partition,
            "enabled": partition_data.get("enabled", False),
            "armed": partition_data.get("armed", False),
            "firing": partition_data.get("firing", False),
            "fired": partition_data.get("fired", False),
            "stay_mode": partition_data.get("stay", False),
        }
