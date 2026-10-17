"""Config flow for ConnectLife integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    config_entry_oauth2_flow,
    device_registry as dr,
    issue_registry as ir,
)
from connectlife.api import (
    LifeConnectAuthError,
    LifeConnectError,
    LifeConnectTermsNotAcceptedError,
)
from connectlife.oauth import OAuthConnectLifeApi, generate_source_id

from .client import create_api
from .const import (
    AUTH_TYPE_OAUTH,
    AUTH_TYPE_PASSWORD,
    CONF_AUTH_TYPE,
    CONF_DEVICES,
    CONF_DEVELOPMENT_MODE,
    CONF_DISABLE_BEEP,
    CONF_EXPOSE_OFFLINE_STATE,
    CONF_SOURCE_ID,
    CONF_TARGET_OVERRIDES,
    CONF_TEST_SERVER_URL,
    CONF_TRIR,
    DOMAIN,
    OVERRIDE_AUTO,
)
from .dictionaries import Dictionaries
from .oauth import ConnectLifeOAuth2Implementation
from .terms import clear_terms_retry_throttle
from .utils import contested_climate_targets

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

STEP_RECONFIGURE_PASSWORD_DATA_SCHEMA = STEP_REAUTH_DATA_SCHEMA.extend(
    {
        vol.Optional(CONF_TRIR, default=False): bool,
    }
)

# Entry data that belongs to one sign-in method, replaced when reconfiguring.
SIGN_IN_DATA_KEYS = (
    CONF_AUTH_TYPE,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_TRIR,
    "auth_implementation",
    "token",
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

    try:
        await api.login()
        appliances = await api.get_appliances()
    except LifeConnectError as ex:
        # The form only shows a generic error, so log the reason.
        _LOGGER.warning("ConnectLife login failed: %s", ex)
        if isinstance(ex, LifeConnectTermsNotAcceptedError):
            raise TermsNotAccepted from ex
        if isinstance(ex, LifeConnectAuthError):
            raise InvalidAuth from ex
        raise CannotConnect from ex

    # Return info that you want to store in the config entry.
    return {
        "title": f"ConnectLife ({data[CONF_USERNAME]})",
        "device_ids": [appliance.device_id for appliance in appliances],
    }


class ConnectLifeConfigFlow(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Handle a config flow for ConnectLife."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

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
        """Choose how to sign in."""
        return self.async_show_menu(
            step_id="user", menu_options=["pick_implementation", "password"]
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how the entry signs in."""
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["pick_implementation", "reconfigure_password"],
        )

    def _configured_elsewhere(self, device_ids: list[str]) -> bool:
        """Whether any of the devices belongs to another enabled ConnectLife entry.

        Disabled entries don't count, so an entry can be replaced by disabling it
        and adding a new one.
        """
        current = None
        if self.source == SOURCE_REAUTH:
            current = self._get_reauth_entry().entry_id
        elif self.source == SOURCE_RECONFIGURE:
            current = self._get_reconfigure_entry().entry_id
        wanted = {(DOMAIN, device_id) for device_id in device_ids}
        device_registry = dr.async_get(self.hass)
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == current or entry.disabled_by is not None:
                continue
            for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
                if device.identifiers & wanted:
                    return True
        return False

    def _update_sign_in(self, entry: ConfigEntry, sign_in: dict[str, Any]) -> ConfigFlowResult:
        """Replace the entry's sign-in data with ``sign_in``, keeping everything else."""
        data = {k: v for k, v in entry.data.items() if k not in SIGN_IN_DATA_KEYS}
        clear_terms_retry_throttle(self.hass, entry.entry_id)
        return self.async_update_reload_and_abort(entry, data={**data, **sign_in})

    async def async_step_pick_implementation(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Sign in in the browser."""
        # The integration may not be set up yet (no entries), so its async_setup
        # hasn't registered the implementation.
        config_entry_oauth2_flow.async_register_implementation(
            self.hass, DOMAIN, ConnectLifeOAuth2Implementation(self.hass)
        )
        return await super().async_step_pick_implementation(user_input)

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create or update the entry after browser sign-in."""
        token = data["token"]["access_token"]

        async def access_token() -> str:
            return token

        try:
            appliances = await OAuthConnectLifeApi(access_token).get_appliances()
        except LifeConnectError:
            return self.async_abort(reason="cannot_connect")
        if self.source == SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()
            return self.async_update_reload_and_abort(
                reauth_entry, data={**reauth_entry.data, **data}
            )
        if self._configured_elsewhere([a.device_id for a in appliances]):
            return self.async_abort(reason="already_configured_elsewhere")
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            return self._update_sign_in(entry, {
                **data,
                CONF_AUTH_TYPE: AUTH_TYPE_OAUTH,
                CONF_SOURCE_ID: entry.data.get(CONF_SOURCE_ID) or generate_source_id(),
            })
        return self.async_create_entry(
            title="ConnectLife",
            data={**data, CONF_AUTH_TYPE: AUTH_TYPE_OAUTH, CONF_SOURCE_ID: generate_source_id()},
        )

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in with username and password."""
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
            except TermsNotAccepted:
                errors["base"] = "terms_not_accepted"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if self._configured_elsewhere(info["device_ids"]):
                    errors["base"] = "already_configured_elsewhere"
                else:
                    return self.async_create_entry(
                        title=info["title"], data=self._entry_data(user_input)
                    )

        return self.async_show_form(
            step_id="password",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reconfigure_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Switch the entry to signing in with username and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except TermsNotAccepted:
                errors["base"] = "terms_not_accepted"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if self._configured_elsewhere(info["device_ids"]):
                    errors["base"] = "already_configured_elsewhere"
                else:
                    return self._update_sign_in(
                        self._get_reconfigure_entry(),
                        {**user_input, CONF_AUTH_TYPE: AUTH_TYPE_PASSWORD},
                    )

        return self.async_show_form(
            step_id="reconfigure_password",
            data_schema=self.add_suggested_values_to_schema(
                STEP_RECONFIGURE_PASSWORD_DATA_SCHEMA, user_input or {}
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
                except TermsNotAccepted:
                    errors["base"] = "terms_not_accepted"
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
        if entry_data.get(CONF_AUTH_TYPE) == AUTH_TYPE_OAUTH:
            return await self.async_step_reauth_oauth()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_oauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask to sign in again in the browser."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_oauth")
        return await self.async_step_pick_implementation()

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
            except TermsNotAccepted:
                errors["base"] = "terms_not_accepted"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Login just succeeded, so don't let the throttle block the reload.
                clear_terms_retry_throttle(self.hass, reauth_entry.entry_id)
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


class TermsNotAccepted(HomeAssistantError):
    """Error to indicate updated Terms & Conditions must be accepted in the app."""


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

        # A device may expose more than one property for the same climate target
        # (e.g. both t_swing_angle and t_up_down for swing_mode). Offer a select
        # per contested target so the user can pin the one their hardware
        # actually honours; "auto" keeps the priority-based binding.
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        appliance = coordinator.data.get(self._device_id)
        contested = (
            contested_climate_targets(appliance, Dictionaries.get_dictionary(appliance))
            if appliance
            else {}
        )

        # Configure the device
        if user_input is not None:
            data = self.config_entry.options.copy()
            data[CONF_DEVICES] = data[CONF_DEVICES].copy() if CONF_DEVICES in data else {}
            overrides = {
                target: user_input[self._override_key(target)]
                for target in contested
                if user_input.get(self._override_key(target), OVERRIDE_AUTO) != OVERRIDE_AUTO
            }
            device_options: dict[str, Any] = {
                CONF_DISABLE_BEEP: user_input[CONF_DISABLE_BEEP],
                CONF_EXPOSE_OFFLINE_STATE: user_input[CONF_EXPOSE_OFFLINE_STATE],
            }
            if overrides:
                device_options[CONF_TARGET_OVERRIDES] = overrides
            data[CONF_DEVICES][self._device_id] = device_options
            if not user_input[CONF_DISABLE_BEEP]:
                ir.async_delete_issue(self.hass, DOMAIN, f"unsupported_beep.{self._device_id}")
            return self.async_create_entry(title="", data=data)

        devices = self.config_entry.options.get(CONF_DEVICES, {})
        device = devices[self._device_id] if self._device_id in devices else {}
        disable_beep = device.get(CONF_DISABLE_BEEP, False)
        expose_offline_state = device.get(CONF_EXPOSE_OFFLINE_STATE, False)
        current_overrides = device.get(CONF_TARGET_OVERRIDES, {})
        schema_dict: dict[Any, Any] = {
            vol.Optional(CONF_DISABLE_BEEP, default=disable_beep): bool,
            vol.Optional(CONF_EXPOSE_OFFLINE_STATE, default=expose_offline_state): bool,
        }
        for target, properties in contested.items():
            default = current_overrides.get(target, OVERRIDE_AUTO)
            if default not in properties:
                default = OVERRIDE_AUTO
            options = {OVERRIDE_AUTO: OVERRIDE_AUTO, **{p: p for p in properties}}
            schema_dict[vol.Optional(self._override_key(target), default=default)] = vol.In(options)

        device_name = (appliance.device_nickname if appliance else self._device_id) or ""
        return self.async_show_form(
            step_id="configure_device",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={"device_name": device_name},
        )

    @staticmethod
    def _override_key(target: str) -> str:
        """Options-form field key for a climate target's property override."""
        return f"{CONF_TARGET_OVERRIDES}_{target}"
