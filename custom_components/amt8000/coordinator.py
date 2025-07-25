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

    def __init__(self, hass, isec_client: ISecClient, password, update_interval: int | float = 4):
        """Initialize the coordinator.

        Parameters
        ----------
        hass: HomeAssistant
            The Home Assistant instance.
        isec_client: ISecClient
            Client used for talking to the alarm panel.
        password: str
            Password for authentication.
        update_interval: int | float, optional
            Poll interval in seconds. Defaults to ``4``.
        """

        super().__init__(
            hass,
            LOGGER,
            name="AMT-8000 Data Polling",
            update_interval=timedelta(seconds=update_interval),
        )
        self.isec_client = isec_client
        self.password = password
        self.next_update = datetime.now()
        self.stored_status = None
        self.attempt = 0
        # Connection lock to prevent simultaneous connections
        self._connection_lock = asyncio.Lock()
        # Track connection failure state
        self.connection_failed = False
        # Track active connections for cleanup
        self._active_connections = set()
        # Track if coordinator is being cleaned up
        self._cleanup_in_progress = False

    async def async_cleanup(self):
        """Perform complete cleanup of coordinator resources."""
        LOGGER.info("Starting coordinator cleanup...")
        self._cleanup_in_progress = True
        
        try:
            # Cancel all pending update tasks
            if hasattr(self, '_unsub_refresh') and self._unsub_refresh:
                try:
                    self._unsub_refresh()
                    self._unsub_refresh = None
                except Exception as e:
                    LOGGER.debug(f"Error canceling refresh subscription: {e}")
            
            # Force close all active connections
            connections_to_close = list(self._active_connections)
            for connection in connections_to_close:
                try:
                    await self._force_close_connection(connection)
                except Exception as e:
                    LOGGER.debug(f"Error force closing connection: {e}")
            
            self._active_connections.clear()
            
            # Force close main client if exists
            if hasattr(self, 'isec_client') and self.isec_client:
                try:
                    await self._force_close_connection(self.isec_client)
                except Exception as e:
                    LOGGER.debug(f"Error closing main client: {e}")
            
            # Reset all internal state
            self.stored_status = None
            self.attempt = 0
            self.connection_failed = False
            self.next_update = datetime.now()
            
            # Clear any locks by creating a new one
            self._connection_lock = asyncio.Lock()
            
            LOGGER.info("Coordinator cleanup completed successfully")
            
        except Exception as e:
            LOGGER.error(f"Error during coordinator cleanup: {e}")
        finally:
            self._cleanup_in_progress = False

    async def _force_close_connection(self, client):
        """Force close a connection aggressively."""
        if client is None:
            return
            
        def _force_close_sync():
            try:
                if hasattr(client, 'client') and client.client:
                    # Set a very short timeout for cleanup
                    client.client.settimeout(0.1)
                    client.client.close()
                    try:
                        client.client.detach()
                    except:
                        pass
                    client.client = None
            except Exception as e:
                LOGGER.debug(f"Force close error (expected): {e}")
        
        # Run the blocking close operation in executor with timeout
        try:
            await asyncio.wait_for(
                self.hass.async_add_executor_job(_force_close_sync),
                timeout=1.0
            )
        except asyncio.TimeoutError:
            LOGGER.warning("Force close operation timed out")
        except Exception as e:
            LOGGER.debug(f"Force close exception: {e}")

    async def _async_update_data(self):
        """Retrieve the current status."""
        # Skip update if cleanup is in progress
        if self._cleanup_in_progress:
            LOGGER.debug("Skipping update - cleanup in progress")
            return self.stored_status

        self.attempt += 1

        if(datetime.now() < self.next_update):
           return self.stored_status

        async with self._connection_lock:
            temp_client = None
            try:
              LOGGER.debug("retrieving amt-8000 updated status...")
              
              # Always create a fresh client for status requests to avoid connection issues
              temp_client = ISecClient(self.isec_client.host, self.isec_client.port)
              self._active_connections.add(temp_client)
              
              temp_client.connect()
              temp_client.auth(self.password)
              status = temp_client.status()
              
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
              
              # Mark connection as successful
              if self.connection_failed:
                  LOGGER.info("Connection recovered successfully")
                  self.connection_failed = False

              return status
              
            except Exception as e:
              LOGGER.error(f"Coordinator update error: {e}")
              
              # Mark connection as failed
              if not self.connection_failed:
                  LOGGER.warning("Connection failure detected")
                  self.connection_failed = True
              
              seconds = min(2 ** self.attempt, 60)  # Cap at 60 seconds
              time_difference = timedelta(seconds=seconds)
              self.next_update = datetime.now() + time_difference
              LOGGER.warning(f"Next retry after {self.next_update}")
              
              # Return stored status if available to avoid marking entities as unavailable
              if self.stored_status:
                  return self.stored_status
              raise

            finally:
               # Always close the temporary client
               if temp_client:
                   try:
                       temp_client.close()
                       self._active_connections.discard(temp_client)
                   except:
                       pass

    async def async_execute_command(self, command_func, description="command"):
        """Execute a command with connection locking and retry logic."""
        # Skip command if cleanup is in progress
        if self._cleanup_in_progress:
            LOGGER.warning(f"Skipping command {description} - cleanup in progress")
            return "failed"

        async with self._connection_lock:
            max_retries = 2
            command_client = None
            
            for attempt in range(max_retries):
                try:
                    LOGGER.debug(f"Executing {description} (attempt {attempt + 1})")
                    
                    # Create a fresh client for commands
                    command_client = ISecClient(self.isec_client.host, self.isec_client.port)
                    self._active_connections.add(command_client)
                    
                    command_client.connect()
                    command_client.auth(self.password)
                    
                    result = command_func(command_client)
                    
                    # Log result for debugging
                    if result in ["armed", "disarmed"]:
                        LOGGER.info(f"Successfully executed {description}: {result}")
                    elif result == "failed":
                        LOGGER.error(f"Command {description} explicitly failed")
                    else:
                        LOGGER.warning(f"Command {description} returned unexpected result: {result}")
                    
                    return result
                    
                except Exception as e:
                    LOGGER.warning(f"Attempt {attempt + 1} failed for {description}: {e}")
                    if attempt == max_retries - 1:
                        LOGGER.error(f"All attempts failed for {description}")
                        raise
                    await asyncio.sleep(0.5)
                    
                finally:
                    # Always close the command client
                    if command_client:
                        try:
                            command_client.close()
                            self._active_connections.discard(command_client)
                        except:
                            pass
                        command_client = None
            
            # Force coordinator refresh after command execution
            # Small delay to let the alarm system process the command
            if not self._cleanup_in_progress:
                await asyncio.sleep(0.2)
                await self.async_request_refresh()
