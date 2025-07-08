from datetime import timedelta, datetime
import asyncio
import logging

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .isec2.client import Client as ISecClient, CommunicationError, AuthError

LOGGER = logging.getLogger(__name__)

class AmtCoordinator(DataUpdateCoordinator):
    """Coordinate the amt status update."""

    def __init__(self, hass, isec_client: ISecClient, password, update_interval: int | float = 4):
        """Initialize the coordinator."""

        super().__init__(
            hass,
            LOGGER,
            name="AMT-8000 Data Polling",
            update_interval=timedelta(seconds=update_interval),
        )
        self.isec_client = isec_client
        self.password = password
        self.connection_failed = False
        self._connection_lock = asyncio.Lock()
        self._cleanup_in_progress = False

    async def _ensure_connected(self):
        """Ensure the client is connected and authenticated."""
        # Check if the client's socket is connected.
        # A simple check for self.isec_client.client might not be enough if the connection dropped.
        if self.isec_client.client is None:
            LOGGER.info("Client not connected. Attempting to connect and authenticate...")
            self.isec_client.connect()  # Can raise CommunicationError
            self.isec_client.auth(self.password)  # Can raise AuthError or CommunicationError
            LOGGER.info("Successfully connected and authenticated.")

    async def async_cleanup(self):
        """Perform complete cleanup of coordinator resources."""
        LOGGER.info("Starting coordinator cleanup...")
        self._cleanup_in_progress = True
        
        async with self._connection_lock:
            if self.isec_client:
                try:
                    self.isec_client.close()
                    LOGGER.info("Persistent client connection closed.")
                except Exception as e:
                    LOGGER.error(f"Error closing main client during cleanup: {e}")
        
        LOGGER.info("Coordinator cleanup completed.")

    async def _async_update_data(self):
        """Retrieve the current status using a persistent connection."""
        if self._cleanup_in_progress:
            LOGGER.debug("Skipping update - cleanup in progress")
            return self.data # Return last known data

        async with self._connection_lock:
            try:
                # Ensure we are connected before fetching status
                await self._ensure_connected()
                
                LOGGER.debug("Retrieving AMT-8000 updated status...")
                status = self.isec_client.status()
                
                # Debug logging for partitions (only when changed)
                if "partitions" in status:
                    enabled_partitions = [p for p, data in status["partitions"].items() if data.get("enabled")]
                    armed_partitions = [p for p, data in status["partitions"].items() if data.get("armed")]
                    current_state = (tuple(enabled_partitions), tuple(armed_partitions))
                    if not hasattr(self, '_last_partition_state') or self._last_partition_state != current_state:
                        LOGGER.info(f"Partition state changed - Enabled: {enabled_partitions}, Armed: {armed_partitions}")
                        self._last_partition_state = current_state

                # If connection was previously marked as failed, it has now recovered
                if self.connection_failed:
                    LOGGER.info("Connection to AMT-8000 recovered.")
                    self.connection_failed = False
                
                return status

            except (CommunicationError, AuthError, TimeoutError, ValueError, OSError) as e:
                # These exceptions indicate a problem with the connection or data.
                if not self.connection_failed:
                    LOGGER.warning(f"Connection to AMT-8000 failed: {e}")
                    self.connection_failed = True
                
                # Close the faulty connection so the next attempt can reconnect
                self.isec_client.close()
                
                # Let the coordinator handle the failure
                raise UpdateFailed(f"Failed to communicate with AMT-8000: {e}") from e

    async def async_execute_command(self, command_func, description="command"):
        """Execute a command with connection locking and retry logic."""
        if self._cleanup_in_progress:
            LOGGER.warning(f"Skipping command '{description}' - cleanup in progress")
            return "failed"

        async with self._connection_lock:
            try:
                # Ensure we are connected before executing the command
                await self._ensure_connected()
                
                LOGGER.debug(f"Executing '{description}'")
                result = command_func(self.isec_client)
                
                LOGGER.info(f"Successfully executed '{description}': {result}")
                
                # After a successful command, immediately request a refresh
                # to get the latest state from the panel.
                await self.async_request_refresh()
                
                return result
                
            except (CommunicationError, AuthError, TimeoutError, ValueError, OSError) as e:
                LOGGER.error(f"Failed to execute command '{description}': {e}")
                
                # Close the faulty connection
                self.isec_client.close()

                # Mark the coordinator for an immediate refresh attempt,
                # which will trigger reconnection logic.
                await self.async_request_refresh()
                return "failed"
