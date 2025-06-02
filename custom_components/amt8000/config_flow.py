"""Add config flow for amt8000 integration."""
import voluptuous as vol
from homeassistant import config_entries, core, exceptions
from homeassistant.core import HomeAssistant

from .const import DOMAIN

import logging

from .isec2.client import Client as ISecClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("port", default=9009): int,
        vol.Required("password"): str,
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
            client.connect()
            client.auth(data["password"])
            status = client.status()
            client.close()
            return {"title": f"AMT-8000 {data['host']}"}
        except Exception as e:
            client.close()
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


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
