"""Config flow for ConnectLife integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
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
from homeassistant.helpers import issue_registry as ir

from .client import create_api
from .const import (
    CONF_DEVICES,
    CONF_DEVELOPMENT_MODE,
    CONF_DISABLE_BEEP,
    CONF_EXPOSE_OFFLINE_STATE,
    CONF_TEST_SERVER_URL,
    CONF_TRIR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Reauth only re-collects credentials; the backend (CONF_TRIR) is preserved
# from the existing entry, so it must not appear in the reauth form.
STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_USER_DATA_SCHEMA = STEP_REAUTH_DATA_SCHEMA.extend(
    {
        vol.Optional(CONF_TRIR, default=False): bool,
        vol.Optional(CONF_DEVELOPMENT_MODE, default=False): bool,
    }
)

# Shown as a second step when development mode is selected, to collect the
# test server URL to authenticate against instead of the ConnectLife API.
STEP_DEVELOPMENT_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(
            CONF_TEST_SERVER_URL,
            description={"suggested_value": "http://localhost:8080"},
        ): str,
    }
)


async def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    test_server_url = data[CONF_TEST_SERVER_URL] if CONF_TEST_SERVER_URL in data else None
    api = create_api(
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        trir=data.get(CONF_TRIR, False),
        test_server_url=test_server_url,
    )

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

    # Credentials carried from the user step to the development step when
    # development mode is selected (auth is deferred until we have the URL).
    _credentials: dict[str, Any] | None = None

    @staticmethod
    def _entry_data(user_input: dict[str, Any]) -> dict[str, Any]:
        """Return the data to persist on the entry (credentials/trir only)."""
        return {
            k: v
            for k, v in user_input.items()
            if k not in (CONF_DEVELOPMENT_MODE, CONF_TEST_SERVER_URL)
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_DEVELOPMENT_MODE):
                # Defer authentication to the development step, which collects
                # the test server URL to authenticate against.
                self._credentials = user_input
                return await self.async_step_development()
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
                return self.async_create_entry(
                    title=info["title"], data=self._entry_data(user_input)
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    async def async_step_development(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the test server URL and authenticate against it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            test_server_url = user_input.get(CONF_TEST_SERVER_URL)
            if not test_server_url:
                errors["base"] = "test_server_required"
            else:
                try:
                    vol.Schema(vol.Url())(test_server_url)  # type: ignore[call-arg]
                except vol.Invalid:
                    errors["base"] = "test_server_invalid"
            if not errors:
                data = {**(self._credentials or {}), CONF_TEST_SERVER_URL: test_server_url}
                try:
                    info = await validate_input(data)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=f"{info['title']} (test server)",
                        data=self._entry_data(self._credentials or {}),
                        options={
                            CONF_DEVELOPMENT_MODE: True,
                            CONF_TEST_SERVER_URL: test_server_url,
                        },
                    )

        return self.async_show_form(
            step_id="development",
            data_schema=self.add_suggested_values_to_schema(
                STEP_DEVELOPMENT_DATA_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when credentials become invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}
        if user_input is not None:
            reauth_entry = self._get_reauth_entry()
            data = {**reauth_entry.data, **user_input}
            try:
                await validate_input(data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
            config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class OptionsFlowHandler(OptionsFlow):
    """Handles options flow for the component."""

    _device_id: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # Select device to configure
        if user_input is not None:
            self._device_id = user_input["device"]
            return await self.async_step_configure_device()

        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        devices = {
            device.device_id: device.device_nickname
            for device in sorted(coordinator.data.values(), key=lambda d: d.device_nickname)
        }

        schema = vol.Schema(
            {
                vol.Optional("device"): vol.In(devices),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_configure_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:

        # Configure the device
        if user_input is not None:
            data = self.config_entry.options.copy()
            data[CONF_DEVICES] = data[CONF_DEVICES].copy() if CONF_DEVICES in data else {}
            data[CONF_DEVICES][self._device_id] = {
                CONF_DISABLE_BEEP: user_input[CONF_DISABLE_BEEP],
                CONF_EXPOSE_OFFLINE_STATE: user_input[CONF_EXPOSE_OFFLINE_STATE],
            }
            if not user_input[CONF_DISABLE_BEEP]:
                ir.async_delete_issue(self.hass, DOMAIN, f"unsupported_beep.{self._device_id}")
            return self.async_create_entry(title="", data=data)

        devices = self.config_entry.options.get(CONF_DEVICES, {})
        device = devices[self._device_id] if self._device_id in devices else {}
        disable_beep = device.get(CONF_DISABLE_BEEP, False)
        expose_offline_state = device.get(CONF_EXPOSE_OFFLINE_STATE, False)
        schema = vol.Schema(
            {
                vol.Optional(CONF_DISABLE_BEEP, default=disable_beep): bool,
                vol.Optional(CONF_EXPOSE_OFFLINE_STATE, default=expose_offline_state): bool,
            }
        )
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        appliance = coordinator.data.get(self._device_id)
        device_name = (appliance.device_nickname if appliance else self._device_id) or ""
        return self.async_show_form(
            step_id="configure_device",
            data_schema=schema,
            description_placeholders={"device_name": device_name},
        )
