"""Tests for browser sign-in tokens and reloading on entry updates."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientConnectionError, ClientResponseError

from connectlife.api import LifeConnectAuthError, LifeConnectError

from custom_components.connectlife import update_listener
from custom_components.connectlife.const import CONF_SOURCE_ID, DOMAIN
from custom_components.connectlife.oauth import create_oauth_api


def _session(error: Exception | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        async_ensure_token_valid=AsyncMock(side_effect=error),
        token={"access_token": "access-1"},
    )


def _response_error(status: int) -> ClientResponseError:
    return ClientResponseError(MagicMock(), (), status=status)


async def test_access_token_comes_from_the_session() -> None:
    entry = SimpleNamespace(data={CONF_SOURCE_ID: "source-1"})
    session = _session()
    api = create_oauth_api(entry, session)  # type: ignore[arg-type]

    await api._fetch_access_token()

    assert api._access_token == "access-1"
    assert api.source_id == "source-1"
    session.async_ensure_token_valid.assert_awaited_once()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_response_error(400), LifeConnectAuthError),
        (_response_error(401), LifeConnectAuthError),
        (_response_error(500), LifeConnectError),
        (ClientConnectionError(), LifeConnectError),
    ],
)
async def test_refresh_errors(error: Exception, expected: type[Exception]) -> None:
    api = create_oauth_api(SimpleNamespace(data={}), _session(error))  # type: ignore[arg-type]

    with pytest.raises(expected) as raised:
        await api._fetch_access_token()
    # A server error must not be taken as a sign-in that expired.
    if expected is LifeConnectError:
        assert not isinstance(raised.value, LifeConnectAuthError)


def _hass(stored_options: dict) -> SimpleNamespace:
    return SimpleNamespace(
        data={DOMAIN: {"entry-1_options": stored_options}},
        config_entries=SimpleNamespace(async_reload=AsyncMock()),
    )


async def test_data_update_does_not_reload() -> None:
    hass = _hass({"devices": {}})
    entry = SimpleNamespace(entry_id="entry-1", options={"devices": {}})

    await update_listener(hass, entry)  # type: ignore[arg-type]

    hass.config_entries.async_reload.assert_not_awaited()


async def test_options_update_reloads() -> None:
    hass = _hass({"devices": {}})
    entry = SimpleNamespace(entry_id="entry-1", options={"devices": {"d": {"disable_beep": True}}})

    await update_listener(hass, entry)  # type: ignore[arg-type]

    hass.config_entries.async_reload.assert_awaited_once_with("entry-1")
