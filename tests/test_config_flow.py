"""Tests for the ConnectLife config flow."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from connectlife.api import LifeConnectAuthError, LifeConnectError

from custom_components.connectlife.config_flow import CannotConnect, InvalidAuth, validate_input

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
