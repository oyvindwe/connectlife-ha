"""Tests for the ConnectLife config flow: choosing the sign-in method and browser sign-in."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.helpers import config_entry_oauth2_flow, device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from connectlife.api import LifeConnectAuthError, LifeConnectError
from connectlife.oauth import OAUTH2_AUTHORIZE_URL, OAUTH2_TOKEN_URL, OAuthConnectLifeApi

from custom_components.connectlife.config_flow import CannotConnect, InvalidAuth, validate_input
from custom_components.connectlife.const import (
    AUTH_TYPE_OAUTH,
    AUTH_TYPE_PASSWORD,
    CONF_AUTH_TYPE,
    CONF_SOURCE_ID,
    DATA_STATE_CLASS_MIGRATION_DONE,
    DOMAIN,
)

REDIRECT_URI = "https://example.com/auth/external/callback"
TOKEN = {
    "access_token": "access-1",
    "refresh_token": "refresh-1",
    "expires_in": 1440,
    "token_type": "bearer",
}


@pytest.fixture(autouse=True, scope="session")
def start_dns_resolver_shutdown_thread():
    """Start pycares' resolver shutdown thread before any test checks for left-behind threads.

    Newer pycares versions start it the first time a resolver is closed, and keep it
    running; the pinned test plugin would report it after the first test that closes
    one (the test HTTP client's).
    """
    import pycares

    channel = pycares.Channel()
    del channel


@pytest.fixture
def mock_setup_entry():
    """Don't set up or unload the created entries."""
    with (
        patch("custom_components.connectlife.async_setup_entry", return_value=True),
        patch("custom_components.connectlife.async_unload_entry", return_value=True),
    ):
        yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(mock_setup_entry, enable_custom_integrations):
    """Load custom_components/connectlife, with entry setup mocked until HA has stopped."""
    yield


@pytest.fixture
async def setup_auth(hass: HomeAssistant) -> None:
    """Set up the auth component, which serves the OAuth callback."""
    assert await async_setup_component(hass, "auth", {})


async def _sign_in(hass, hass_client_no_auth, aioclient_mock, result) -> dict:
    """Follow the browser sign-in from the external step to the flow result."""
    flow_id = result["flow_id"]
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    assert result["url"].startswith(OAUTH2_AUTHORIZE_URL)

    state = config_entry_oauth2_flow._encode_jwt(
        hass, {"flow_id": flow_id, "redirect_uri": REDIRECT_URI}
    )
    client = await hass_client_no_auth()
    response = await client.get(f"/auth/external/callback?code=code-1&state={state}")
    assert response.status == 200
    await client.close()

    aioclient_mock.post(OAUTH2_TOKEN_URL, json=TOKEN)
    return await hass.config_entries.flow.async_configure(flow_id)


async def test_user_step_offers_both_sign_in_methods(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["pick_implementation", "password"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "password"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "password"


@pytest.mark.usefixtures("current_request_with_host", "setup_auth")
async def test_browser_sign_in_creates_entry(
    hass: HomeAssistant, hass_client_no_auth, aioclient_mock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "pick_implementation"}
    )

    with patch.object(OAuthConnectLifeApi, "get_appliances", AsyncMock(return_value=[])):
        result = await _sign_in(hass, hass_client_no_auth, aioclient_mock, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_AUTH_TYPE] == AUTH_TYPE_OAUTH
    assert data[CONF_SOURCE_ID].startswith("td001002000")
    assert data["auth_implementation"] == DOMAIN
    assert data["token"]["access_token"] == "access-1"


@pytest.mark.usefixtures("current_request_with_host", "setup_auth")
async def test_browser_sign_in_aborts_when_api_fails(
    hass: HomeAssistant, hass_client_no_auth, aioclient_mock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "pick_implementation"}
    )

    with patch.object(
        OAuthConnectLifeApi, "get_appliances", AsyncMock(side_effect=LifeConnectError("down"))
    ):
        result = await _sign_in(hass, hass_client_no_auth, aioclient_mock, result)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.usefixtures("current_request_with_host", "setup_auth")
async def test_reauth_signs_in_again_and_keeps_source_id(
    hass: HomeAssistant, hass_client_no_auth, aioclient_mock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_TYPE: AUTH_TYPE_OAUTH,
            CONF_SOURCE_ID: "source-1",
            "auth_implementation": DOMAIN,
            "token": {**TOKEN, "access_token": "expired", "expires_at": 0},
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_oauth"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    with patch.object(OAuthConnectLifeApi, "get_appliances", AsyncMock(return_value=[])):
        result = await _sign_in(hass, hass_client_no_auth, aioclient_mock, result)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"]["access_token"] == "access-1"
    assert entry.data[CONF_SOURCE_ID] == "source-1"
    assert entry.data[CONF_AUTH_TYPE] == AUTH_TYPE_OAUTH


APPLIANCES = [SimpleNamespace(device_id="device-1")]


def _password_entry(hass: HomeAssistant, **kwargs) -> MockConfigEntry:
    """A password entry owning device-1."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user@example.com", "password": "secret", DATA_STATE_CLASS_MIGRATION_DONE: True},
        **kwargs,
    )
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "device-1")}
    )
    return entry


def _password_api():
    """Patch the password login to succeed for an account with device-1."""
    api = SimpleNamespace(login=AsyncMock(), get_appliances=AsyncMock(return_value=APPLIANCES))
    return patch("custom_components.connectlife.config_flow.create_api", return_value=api)


async def _start_browser_sign_in(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "pick_implementation"}
    )


@pytest.mark.usefixtures("current_request_with_host", "setup_auth")
async def test_browser_sign_in_aborts_when_devices_belong_to_another_entry(
    hass: HomeAssistant, hass_client_no_auth, aioclient_mock
) -> None:
    _password_entry(hass)
    result = await _start_browser_sign_in(hass)

    with patch.object(OAuthConnectLifeApi, "get_appliances", AsyncMock(return_value=APPLIANCES)):
        result = await _sign_in(hass, hass_client_no_auth, aioclient_mock, result)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured_elsewhere"


@pytest.mark.usefixtures("current_request_with_host", "setup_auth")
async def test_browser_sign_in_allowed_when_other_entry_is_disabled(
    hass: HomeAssistant, hass_client_no_auth, aioclient_mock
) -> None:
    _password_entry(hass, disabled_by=ConfigEntryDisabler.USER)
    result = await _start_browser_sign_in(hass)

    with patch.object(OAuthConnectLifeApi, "get_appliances", AsyncMock(return_value=APPLIANCES)):
        result = await _sign_in(hass, hass_client_no_auth, aioclient_mock, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_password_sign_in_shows_error_when_devices_belong_to_another_entry(
    hass: HomeAssistant,
) -> None:
    _password_entry(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "password"}
    )

    with _password_api():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"username": "user@example.com", "password": "secret"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "already_configured_elsewhere"}


@pytest.mark.usefixtures("current_request_with_host", "setup_auth")
async def test_reconfigure_switches_to_browser_sign_in(
    hass: HomeAssistant, hass_client_no_auth, aioclient_mock
) -> None:
    entry = _password_entry(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "pick_implementation"}
    )
    with patch.object(OAuthConnectLifeApi, "get_appliances", AsyncMock(return_value=APPLIANCES)):
        result = await _sign_in(hass, hass_client_no_auth, aioclient_mock, result)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_AUTH_TYPE] == AUTH_TYPE_OAUTH
    assert entry.data["token"]["access_token"] == "access-1"
    assert entry.data[CONF_SOURCE_ID].startswith("td001002000")
    assert "username" not in entry.data
    assert "password" not in entry.data
    assert entry.data[DATA_STATE_CLASS_MIGRATION_DONE] is True


async def test_reconfigure_switches_to_password(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_TYPE: AUTH_TYPE_OAUTH,
            CONF_SOURCE_ID: "source-1",
            "auth_implementation": DOMAIN,
            "token": TOKEN,
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_password"}
    )
    with _password_api():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"username": "user@example.com", "password": "secret"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_AUTH_TYPE] == AUTH_TYPE_PASSWORD
    assert entry.data["username"] == "user@example.com"
    assert "token" not in entry.data
    assert "auth_implementation" not in entry.data


DATA = {"username": "user@example.com", "password": "secret"}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LifeConnectAuthError("Failed to login. Code: 403042 Message: 'Invalid LoginID'"), InvalidAuth),
        (LifeConnectError("Unexpected response from getJWT: status=503"), CannotConnect),
    ],
)
async def test_validate_input_logs_login_failure(caplog, error, expected) -> None:
    api = AsyncMock()
    api.login.side_effect = error
    with (
        patch("custom_components.connectlife.config_flow.create_api", return_value=api),
        caplog.at_level(logging.WARNING),
        pytest.raises(expected),
    ):
        await validate_input(DATA)

    assert f"ConnectLife login failed: {error}" in caplog.text
    assert "secret" not in caplog.text
