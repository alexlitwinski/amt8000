from datetime import timedelta, datetime
import asyncio
import time

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

    async def _async_update_data(self):
        """Retrieve the current status."""
        self.attempt += 1

        if(datetime.now() < self.next_update):
           return self.stored_status

        async with self._connection_lock:
            temp_client = None
            try:
                LOGGER.debug("retrieving amt-8000 updated status...")
                
                # Sempre cria um novo cliente para cada operação
                temp_client = ISecClient(self.isec_client.host, self.isec_client.port)
                
                # Conecta com retry
                max_connect_retries = 3
                for retry in range(max_connect_retries):
                    try:
                        await self.hass.async_add_executor_job(temp_client.connect)
                        break
                    except Exception as e:
                        if retry == max_connect_retries - 1:
                            raise
                        LOGGER.warning(f"Connection attempt {retry + 1} failed, retrying...")
                        await asyncio.sleep(1)
                
                # Autentica
                await self.hass.async_add_executor_job(temp_client.auth, self.password)
                
                # Pequeno delay após auth
                await asyncio.sleep(0.2)
                
                # Obtém status
                status = await self.hass.async_add_executor_job(temp_client.status)
                
                # Verifica estrutura dos dados
                partitions_count = len(status.get("partitions", {}))
                zones_count = len(status.get("zones", {}))
                LOGGER.debug(f"AMT-8000 status retrieved - Partitions: {partitions_count}, Zones: {zones_count}, System Status: {status.get('status', 'unknown')}")
                
                # Debug logging para partições (apenas quando mudou)
                if "partitions" in status:
                    enabled_partitions = [p for p, data in status["partitions"].items() if data.get("enabled")]
                    armed_partitions = [p for p, data in status["partitions"].items() if data.get("armed")]
                    
                    # Apenas registra se diferente do último estado conhecido
                    current_state = (tuple(enabled_partitions), tuple(armed_partitions))
                    if not hasattr(self, '_last_partition_state') or self._last_partition_state != current_state:
                        LOGGER.info(f"Partition state changed - Enabled: {enabled_partitions}, Armed: {armed_partitions}")
                        self._last_partition_state = current_state
                
                # Debug logging para zonas (reduzido)
                if "zones" in status:
                    enabled_zones = [z for z, data in status["zones"].items() if data.get("enabled")]
                    open_zones = [z for z, data in status["zones"].items() if data.get("open") or data.get("violated")]
                    LOGGER.debug(f"Enabled zones: {len(enabled_zones)}, Open/violated zones: {open_zones}")

                self.stored_status = status
                self.attempt = 0
                self.next_update = datetime.now()
                
                # Marca conexão como bem-sucedida
                if self.connection_failed:
                    LOGGER.info("Connection recovered successfully")
                    self.connection_failed = False

                return status
                
            except Exception as e:
                LOGGER.error(f"Coordinator update error: {e}")
                
                # Marca conexão como falha
                if not self.connection_failed:
                    LOGGER.warning("Connection failure detected")
                    self.connection_failed = True
                
                seconds = min(2 ** self.attempt, 60)  # Máximo de 60 segundos
                time_difference = timedelta(seconds=seconds)
                self.next_update = datetime.now() + time_difference
                LOGGER.warning(f"Next retry after {self.next_update}")
                
                # Retorna status armazenado se disponível para evitar marcar entidades como indisponíveis
                if self.stored_status:
                    return self.stored_status
                raise

            finally:
                # Sempre fecha o cliente temporário
                if temp_client:
                    try:
                        await self.hass.async_add_executor_job(temp_client.close)
                    except Exception as e:
                        LOGGER.debug(f"Error closing temporary client: {e}")

    async def async_execute_command(self, command_func, description="command"):
        """Execute a command with connection locking and retry logic."""
        async with self._connection_lock:
            max_retries = 2
            command_client = None
            
            for attempt in range(max_retries):
                try:
                    LOGGER.debug(f"Executing {description} (attempt {attempt + 1})")
                    
                    # Cria um novo cliente para comandos
                    command_client = ISecClient(self.isec_client.host, self.isec_client.port)
                    
                    # Conecta
                    await self.hass.async_add_executor_job(command_client.connect)
                    
                    # Autentica
                    await self.hass.async_add_executor_job(command_client.auth, self.password)
                    
                    # Pequeno delay após auth
                    await asyncio.sleep(0.2)
                    
                    # Executa o comando
                    result = await self.hass.async_add_executor_job(command_func, command_client)
                    
                    # Registra resultado para debug
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
                    # Sempre fecha o cliente de comando
                    if command_client:
                        try:
                            await self.hass.async_add_executor_job(command_client.close)
                        except Exception as e:
                            LOGGER.debug(f"Error closing command client: {e}")
                    command_client = None
            
            # Força atualização do coordinator após execução do comando
            # Pequeno delay para deixar o sistema de alarme processar o comando
            await asyncio.sleep(0.5)
            await self.async_request_refresh()

    async def async_shutdown(self):
        """Shutdown coordinator."""
        await super().async_shutdown()
