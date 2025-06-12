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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the entries for amt-8000."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    
    # Always create a fresh coordinator for alarm control panels to avoid issues
    coordinator_key = f"{DOMAIN}_coordinator_{config_entry.entry_id}"
    
    LOGGER.info("Creating fresh coordinator for alarm control panels")
    isec_client = ISecClient(data["host"], data["port"])
    # Get update interval from config or options, default to 4 seconds if not present
    update_interval = data.get("update_interval", 4)
    if config_entry.options:
        update_interval = config_entry.options.get("update_interval", update_interval)
    coordinator = AmtCoordinator(hass, isec_client, data["password"], update_interval)
    
    try:
        await coordinator.async_config_entry_first_refresh()
        hass.data[coordinator_key] = coordinator
        LOGGER.info(f"Coordinator initialized with update interval: {update_interval} seconds")
    except Exception as e:
        LOGGER.error(f"Failed to initialize coordinator: {e}")
        raise
    
    LOGGER.info('Setting up 5 alarm control panels (partitions 1-5)...')
    
    # Create 5 partition entities (1-5)
    panels = []
    for partition in range(1, 6):
        panels.append(AmtAlarmPanel(coordinator, data['password'], partition))
    
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
