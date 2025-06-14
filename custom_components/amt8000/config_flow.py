"""Add config flow for amt8000 integration."""
import voluptuous as vol
from homeassistant import config_entries, core, exceptions
from homeassistant.core import HomeAssistant

from .const import DOMAIN

import logging
import asyncio

from .isec2.client import Client as ISecClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("port", default=9009): int,
        vol.Required("password"): str,
        vol.Required("update_interval", default=10): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
    }
)


async def validate_input(hass: HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    
    def _test_connection():
        """Test connection in a separate thread to avoid blocking."""
        client = ISecClient(data["host"], data["port"])
        try:
            # Tenta conectar com retry
            max_retries = 3
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    _LOGGER.debug(f"Connection test attempt {attempt + 1}/{max_retries}")
                    client.connect()
                    client.auth(data["password"])
                    status = client.status()
                    client.close()
                    
                    # Aguarda um pouco antes de fechar para garantir que a central processe
                    import time
                    time.sleep(0.5)
                    
                    return {"title": f"AMT-8000 {data['host']}"}
                    
                except Exception as e:
                    last_error = e
                    _LOGGER.warning(f"Connection test attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(2)  # Aguarda 2 segundos entre tentativas
                    
            # Se todas as tentativas falharam
            raise last_error
                    
        except Exception as e:
            _LOGGER.error(f"Connection test failed after all attempts: {e}")
            try:
                client.close()
            except:
                pass
            raise e
    
    # Run the blocking connection test in an executor
    try:
        result = await hass.async_add_executor_job(_test_connection)
        return result
    except Exception as e:
        _LOGGER.error(f"Connection test failed: {e}")
        raise CannotConnect from e


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for amt8000 integration."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for AMT-8000 integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            _LOGGER.info(f"Saving options: {user_input}")
            # Update the config entry with new options
            return self.async_create_entry(title="", data=user_input)

        # Get current values
        current_update_interval = self.config_entry.data.get("update_interval", 10)
        if self.config_entry.options and "update_interval" in self.config_entry.options:
            current_update_interval = self.config_entry.options["update_interval"]
        
        _LOGGER.info(f"Current options flow - config data: {self.config_entry.data}")
        _LOGGER.info(f"Current options flow - existing options: {self.config_entry.options}")
        _LOGGER.info(f"Current options flow - using interval: {current_update_interval}")
        
        options_schema = vol.Schema(
            {
                vol.Required(
                    "update_interval", 
                    default=current_update_interval
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
