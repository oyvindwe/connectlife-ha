"""Push updates from the ConnectLife cloud over a WebSocket (beta).

The cloud pushes a device's status within seconds of a change. While connected, the coordinator polls only as a
safety net; when the connection is lost, it polls every minute again until reconnected.
"""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import TYPE_CHECKING

import aiohttp
from connectlife.api import LifeConnectError
from connectlife.push import ConnectLifePush, PushConnected, PushOnline, PushStatus

if TYPE_CHECKING:
    from .coordinator import ConnectLifeCoordinator

_LOGGER = logging.getLogger(__name__)

# Delay before reconnecting, doubled after each failed attempt up to the maximum.
RECONNECT_DELAY = 10
MAX_RECONNECT_DELAY = 600
# A connection that lasted this long resets the delay.
STABLE_CONNECTION = 600


class PushListener:
    """Keeps a push connection open for a coordinator and applies what it receives."""

    def __init__(self, coordinator: ConnectLifeCoordinator, phone_code: str) -> None:
        self._coordinator = coordinator
        self._push = ConnectLifePush(coordinator.api, phone_code)

    async def run(self) -> None:
        """Connect, and reconnect with a growing delay, until cancelled."""
        delay = RECONNECT_DELAY
        while True:
            started = monotonic()
            try:
                async for event in self._push.listen():
                    await self._handle(event)
                _LOGGER.debug("Push connection closed")
            except (LifeConnectError, aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("Push connection failed: %s", err)
            except Exception:  # noqa: BLE001 - keep reconnecting, polling covers the gap
                _LOGGER.exception("Unexpected error in push connection")
            if monotonic() - started >= STABLE_CONNECTION:
                delay = RECONNECT_DELAY
            if self._coordinator.push_connected:
                await self._coordinator.async_set_push_connected(False)
            _LOGGER.debug("Reconnecting push in %d s", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)

    async def _handle(self, event) -> None:
        if isinstance(event, PushConnected):
            _LOGGER.debug("Push connected")
            await self._coordinator.async_set_push_connected(True)
        elif isinstance(event, PushStatus):
            self._coordinator.apply_push_status(event.puid, event.properties)
        elif isinstance(event, PushOnline):
            self._coordinator.apply_push_online(event.puid, event.online)
