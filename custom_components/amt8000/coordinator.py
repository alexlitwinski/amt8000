from datetime import timedelta, datetime
import asyncio

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)

from .isec2.client import Client as ISecClient

import logging

LOGGER = logging.getLogger(__name__)

class AmtCoordinator(DataUpdateCoordinator):
    """Coordinate the amt status update."""

    def __init__(self, hass, isec_client: ISecClient, password):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="AMT-8000 Data Polling",
            update_interval=timedelta(seconds=4),  # Changed from 10 to 4 seconds
        )
        self.isec_client = isec_client
        self.password = password
        self.next_update = datetime.now()
        self.stored_status = None
        self.attempt = 0
        # Connection lock to prevent simultaneous connections
        self._connection_lock = asyncio.Lock()

    async def _async_update_data(self):
        """Retrieve the current status."""
        self.attempt += 1

        if(datetime.now() < self.next_update):
           return self.stored_status

        async with self._connection_lock:
            try:
              LOGGER.debug("retrieving amt-8000 updated status...")
              
              # Use the main client for status requests
              self.isec_client.connect()
              self.isec_client.auth(self.password)
              status = self.isec_client.status()
              self.isec_client.close()
              
              # Verify data structure
              partitions_count = len(status.get("partitions", {}))
              zones_count = len(status.get("zones", {}))
              LOGGER.debug(f"AMT-8000 status retrieved - Partitions: {partitions_count}, Zones: {zones_count}, System Status: {status.get('status', 'unknown')}")
              
              # Debug logging for partitions (only when changed)
              if "partitions" in status:
                  enabled_partitions = [p for p, data in status["partitions"].items() if data.get("enabled")]
                  armed_partitions = [p for p, data in status["partitions"].items() if data.get("armed")]
                  
                  # Only log if different from last known state
                  current_state = (tuple(enabled_partitions), tuple(armed_partitions))
                  if not hasattr(self, '_last_partition_state') or self._last_partition_state != current_state:
                      LOGGER.info(f"Partition state changed - Enabled: {enabled_partitions}, Armed: {armed_partitions}")
                      self._last_partition_state = current_state
              
              # Debug logging for zones (reduced)
              if "zones" in status:
                  enabled_zones = [z for z, data in status["zones"].items() if data.get("enabled")]
                  open_zones = [z for z, data in status["zones"].items() if data.get("open") or data.get("violated")]
                  LOGGER.debug(f"Enabled zones: {len(enabled_zones)}, Open/violated zones: {open_zones}")

              self.stored_status = status
              self.attempt = 0
              self.next_update = datetime.now()

              return status
              
            except Exception as e:
              LOGGER.error(f"Coordinator update error: {e}")
              seconds = 2 ** self.attempt
              time_difference = timedelta(seconds=seconds)
              self.next_update = datetime.now() + time_difference
              LOGGER.warning(f"Next retry after {self.next_update}")

            finally:
               try:
                   self.isec_client.close()
               except:
                   pass

    async def async_execute_command(self, command_func, description="command"):
        """Execute a command with connection locking and retry logic."""
        async with self._connection_lock:
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    LOGGER.debug(f"Executing {description} (attempt {attempt + 1})")
                    
                    # Create a fresh client for commands
                    command_client = ISecClient(self.isec_client.host, self.isec_client.port)
                    command_client.connect()
                    command_client.auth(self.password)
                    
                    result = command_func(command_client)
                    
                    command_client.close()
                    
                    # Log result for debugging
                    if result in ["armed", "disarmed"]:
                        LOGGER.info(f"Successfully executed {description}: {result}")
                    elif result == "failed":
                        LOGGER.error(f"Command {description} explicitly failed")
                    else:
                        LOGGER.warning(f"Command {description} returned unexpected result: {result}")
                    
                    # Force coordinator refresh after command (successful or not)
                    await self.async_request_refresh()
                    
                    return result
                    
                except Exception as e:
                    LOGGER.warning(f"Attempt {attempt + 1} failed for {description}: {e}")
                    if attempt == max_retries - 1:
                        LOGGER.error(f"All attempts failed for {description}")
                        raise
                    await asyncio.sleep(0.5)
