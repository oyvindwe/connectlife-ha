"""Config flow for ConnectLife integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_DEVELOPMENT_MODE, CONF_TEST_SERVER_URL, DOMAIN
from connectlife.api import ConnectLifeApi

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    test_server_url = data[CONF_TEST_SERVER_URL] if CONF_TEST_SERVER_URL in data else None
    api = ConnectLifeApi(data[CONF_USERNAME], data[CONF_PASSWORD], test_server_url)

    if not await api.authenticate():
        raise InvalidAuth

    # If you cannot connect:
    # throw CannotConnect
    # If the authentication is wrong:
    # InvalidAuth

    # Return info that you want to store in the config entry.
    return {"title": f"ConnectLife ({data[CONF_USERNAME]})"}


class ConnectLifeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ConnectLife."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(user_input)
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

    @staticmethod
    @callback
    def async_get_options_flow(
            config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class OptionsFlowHandler(OptionsFlow):
    """Handles options flow for the component."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Manage the options."""

        if user_input is not None:
            errors: dict[str, str] = {}
            development_mode = user_input.get(CONF_DEVELOPMENT_MODE)
            test_server_url = user_input.get(CONF_TEST_SERVER_URL)
            _LOGGER.debug("development_mode=%s, test_server_url=%s", str(development_mode), test_server_url)
            if test_server_url:
                try:
                    vol.Schema(vol.Url())(test_server_url)
                except vol.Invalid:
                    errors["base"] = "test_server_invalid"
            if development_mode and not test_server_url:
                errors["base"] = "test_server_required"
            _LOGGER.debug(errors)
            if errors:
                return self._show_form(development_mode, test_server_url, errors)

            data = {
                CONF_DEVELOPMENT_MODE: development_mode,
                CONF_TEST_SERVER_URL: test_server_url
            }
            return self.async_create_entry(title="", data=data)

        development_mode = self.config_entry.options.get(CONF_DEVELOPMENT_MODE, False)
        test_server_url = self.config_entry.options.get(CONF_TEST_SERVER_URL, "http://localhost:8080")
        return self._show_form(development_mode, test_server_url)

    def _show_form(self, development_mode: bool, test_server_url: str, errors: dict[str, str] = None):
        schema = vol.Schema(
            {
                vol.Optional(CONF_DEVELOPMENT_MODE, default=development_mode): bool,
                vol.Optional(CONF_TEST_SERVER_URL, description={"suggested_value": test_server_url}): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
