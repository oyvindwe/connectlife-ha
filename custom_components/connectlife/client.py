"""Backend selection for the ConnectLife integration."""

from __future__ import annotations

from connectlife.api import ConnectLifeApi
from connectlife.trir import TrirConnectLifeApi


def create_api(
    username: str,
    password: str,
    *,
    trir: bool = False,
    test_server_url: str | None = None,
) -> ConnectLifeApi:
    """Create a ConnectLife API client for the configured backend."""
    if trir:
        return TrirConnectLifeApi(username, password, test_server_url)  # type: ignore[arg-type]
    return ConnectLifeApi(username, password, test_server_url)  # type: ignore[arg-type]
