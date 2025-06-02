"""Defines the alarm control panels for amt-8000."""
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity, AlarmControlPanelEntityFeature

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
    """Set up the entries for amt-8000."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    isec_client = ISecClient(data["host"], data["port"])
    coordinator = AmtCoordinator(hass, isec_client, data["password"])
    LOGGER.info('setting up alarm control panels...')
    
    # Create 5 partition entities (1-5)
    panels = []
    for partition in range(1, 6):
        panels.append(AmtAlarmPanel(coordinator, isec_client, data['password'], partition))
    
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
        self.status = None
        self.password = password
        self.partition = partition
        self._is_on = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the stored value on coordinator updates."""
        self.status = self.coordinator.data
        
        # Debug logging to check partition-specific data (reduced frequency)
        if self.status and "partitions" in self.status:
            partitions = self.status["partitions"]
            if self.partition in partitions:
                partition_data = partitions[self.partition]
                # Only log every 5th update to reduce spam
                if hasattr(self, '_debug_counter'):
                    self._debug_counter += 1
                else:
                    self._debug_counter = 1
                    
                if self._debug_counter % 5 == 0:
                    main_status = self.status.get('status', 'unknown')
                    LOGGER.debug(f"Partition {self.partition}: armed={partition_data.get('armed')}, stay={partition_data.get('stay')}, main_status={main_status}")
            else:
                LOGGER.warning(f"Partition {self.partition} not found in payload data")
        
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
    def state(self) -> str:
        """Return the state of the entity."""
        if self.status is None:
            return "unknown"

        if self.status['siren'] == True:
            return "triggered"

        # Get partition-specific state from coordinator data
        partitions = self.status.get("partitions", {})
        partition_data = partitions.get(self.partition, {})
        
        if partition_data.get("armed", False):
            self._is_on = True
            if partition_data.get("stay", False):
                return "armed_home"
            else:
                return "armed_away"
        else:
            self._is_on = False
            return "disarmed"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self.status is None:
            return False
        
        partitions = self.status.get("partitions", {})
        partition_data = partitions.get(self.partition, {})
        
        # For debugging - temporarily make all partitions available
        # Later we can add logic to check if partition is actually configured
        available = partition_data.get("enabled", True)  # Default to True for now
        
        if not available:
            LOGGER.debug(f"Partition {self.partition} marked as unavailable - enabled: {partition_data.get('enabled', 'missing')}")
        
        return available

    def _arm_away_command(self, client):
        """Arm partition in away mode command function"""
        result = client.arm_system(self.partition)
        if result == "armed":
            return 'armed_away'
        return result

    def _disarm_command(self, client):
        """Disarm partition command function"""
        result = client.disarm_system(self.partition)
        if result == "disarmed":
            return 'disarmed'
        return result

    def _trigger_alarm_command(self, client):
        """Trigger Alarm command function"""
        result = client.panic(1)
        if result == "triggered":
            return "triggered"
        return result

    def alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        # Use coordinator's command execution
        import asyncio
        asyncio.create_task(self.coordinator.async_execute_command(
            self._disarm_command,
            f"disarm partition {self.partition}"
        ))

    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        await self.coordinator.async_execute_command(
            self._disarm_command,
            f"disarm partition {self.partition}"
        )

    def alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        # Use coordinator's command execution
        import asyncio
        asyncio.create_task(self.coordinator.async_execute_command(
            self._arm_away_command,
            f"arm away partition {self.partition}"
        ))

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        await self.coordinator.async_execute_command(
            self._arm_away_command,
            f"arm away partition {self.partition}"
        )

    def alarm_trigger(self, code=None) -> None:
        """Send alarm trigger command."""
        import asyncio
        asyncio.create_task(self.coordinator.async_execute_command(
            self._trigger_alarm_command,
            f"trigger alarm partition {self.partition}"
        ))

    async def async_alarm_trigger(self, code=None) -> None:
        """Send alarm trigger command."""
        await self.coordinator.async_execute_command(
            self._trigger_alarm_command,
            f"trigger alarm partition {self.partition}"
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if entity is on."""
        return self._is_on

    def turn_on(self, **kwargs: Any) -> None:
        import asyncio
        asyncio.create_task(self.coordinator.async_execute_command(
            self._arm_away_command,
            f"turn on partition {self.partition}"
        ))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self.coordinator.async_execute_command(
            self._arm_away_command,
            f"turn on partition {self.partition}"
        )

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        import asyncio
        asyncio.create_task(self.coordinator.async_execute_command(
            self._disarm_command,
            f"turn off partition {self.partition}"
        ))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.coordinator.async_execute_command(
            self._disarm_command,
            f"turn off partition {self.partition}"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.status is None:
            return {"partition_number": self.partition}
        
        partitions = self.status.get("partitions", {})
        partition_data = partitions.get(self.partition, {})
        
        return {
            "partition_number": self.partition,
            "enabled": partition_data.get("enabled", False),
            "armed": partition_data.get("armed", False),
            "firing": partition_data.get("firing", False),
            "fired": partition_data.get("fired", False),
            "stay_mode": partition_data.get("stay", False),
        }
