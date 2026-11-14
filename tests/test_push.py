"""Tests for push updates (push.py and the coordinator's push handling)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from connectlife.api import LifeConnectError
from connectlife.push import PushConnected, PushOnline, PushStatus

from custom_components.connectlife import push as push_module
from custom_components.connectlife.coordinator import (
    PUSH_UPDATE_INTERVAL,
    UPDATE_INTERVAL,
    ConnectLifeCoordinator,
)
from custom_components.connectlife.push import PushListener


def _coordinator(*appliances) -> ConnectLifeCoordinator:
    coordinator = ConnectLifeCoordinator.__new__(ConnectLifeCoordinator)
    coordinator.data = {a.device_id: a for a in appliances}
    coordinator.api = MagicMock()
    coordinator.push_connected = False
    coordinator._commanded = {}
    coordinator.update_interval = UPDATE_INTERVAL
    coordinator.async_update_listeners = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def _appliance(changed: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        device_id="d1",
        puid="pu1",
        device_nickname="Washer",
        update_status=MagicMock(return_value={"t_power"} if changed else set()),
        status_list={"t_power": 1},
        update_online=MagicMock(return_value=changed),
    )


def test_push_status_updates_and_notifies() -> None:
    appliance = _appliance()
    coordinator = _coordinator(appliance)

    coordinator.apply_push_status("pu1", {"t_power": "1"})

    appliance.update_status.assert_called_once_with({"t_power": "1"})
    coordinator.async_update_listeners.assert_called_once()


def test_push_status_unchanged_does_not_notify() -> None:
    coordinator = _coordinator(_appliance(changed=False))

    coordinator.apply_push_status("pu1", {"t_power": "1"})

    coordinator.async_update_listeners.assert_not_called()


def test_push_for_unknown_device_is_ignored() -> None:
    appliance = _appliance()
    coordinator = _coordinator(appliance)

    coordinator.apply_push_status("other", {"t_power": "1"})
    coordinator.apply_push_online("other", False)

    appliance.update_status.assert_not_called()
    appliance.update_online.assert_not_called()
    coordinator.async_update_listeners.assert_not_called()


def test_push_online_updates_and_notifies() -> None:
    appliance = _appliance()
    coordinator = _coordinator(appliance)

    coordinator.apply_push_online("pu1", False)

    appliance.update_online.assert_called_once_with(False)
    coordinator.async_update_listeners.assert_called_once()


async def test_push_connected_polls_slowly_and_refreshes() -> None:
    coordinator = _coordinator()

    await coordinator.async_set_push_connected(True)
    assert coordinator.push_connected
    assert coordinator.update_interval == PUSH_UPDATE_INTERVAL

    await coordinator.async_set_push_connected(False)
    assert not coordinator.push_connected
    assert coordinator.update_interval == UPDATE_INTERVAL
    assert coordinator.async_request_refresh.await_count == 2


class _Stop(Exception):
    """Ends PushListener.run() in tests, in place of the task being cancelled."""


async def _run(listener: PushListener, sessions: list) -> list[float]:
    """Run the listener over the given sessions (event lists, or an exception); return the reconnect delays."""
    remaining = iter(sessions)

    async def listen():
        session = next(remaining)
        if isinstance(session, Exception):
            raise session
        for event in session:
            yield event

    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) == len(sessions):
            raise _Stop

    listener._push = SimpleNamespace(listen=listen)
    with patch.object(push_module.asyncio, "sleep", sleep), pytest.raises(_Stop):
        await listener.run()
    return delays


async def test_listener_applies_events_and_falls_back_to_polling() -> None:
    appliance = _appliance()
    coordinator = _coordinator(appliance)
    listener = PushListener(coordinator, "phone")

    await _run(listener, [[PushConnected(), PushStatus("pu1", {"t_power": "1"}), PushOnline("pu1", True)]])

    appliance.update_status.assert_called_once_with({"t_power": "1"})
    appliance.update_online.assert_called_once_with(True)
    # Connected, then back to polling every minute when the connection ended.
    assert not coordinator.push_connected
    assert coordinator.update_interval == UPDATE_INTERVAL
    assert coordinator.async_request_refresh.await_count == 2


async def test_listener_backs_off_on_failures() -> None:
    coordinator = _coordinator()
    listener = PushListener(coordinator, "phone")

    delays = await _run(listener, [LifeConnectError("down"), TimeoutError(), RuntimeError("bug"), []])

    assert delays == [10, 20, 40, 80]
    # Never connected, so no switch back to polling was needed.
    coordinator.async_request_refresh.assert_not_awaited()


async def test_listener_stops_when_cancelled() -> None:
    coordinator = _coordinator()
    listener = PushListener(coordinator, "phone")
    started = asyncio.Event()

    async def listen():
        started.set()
        await asyncio.Event().wait()
        yield PushConnected()  # pragma: no cover

    listener._push = SimpleNamespace(listen=listen)
    task = asyncio.create_task(listener.run())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_poll_logs_changes_push_missed(caplog: pytest.LogCaptureFixture) -> None:
    old = SimpleNamespace(device_id="d1", device_nickname="Washer", status_list={"t_power": 0, "t_temp": 20})
    new = SimpleNamespace(device_id="d1", device_nickname="Washer", status_list={"t_power": 1, "t_temp": 20})
    coordinator = _coordinator(old)

    with caplog.at_level("DEBUG", logger="custom_components.connectlife.coordinator"):
        coordinator._log_missed_pushes({"d1": new})

    assert "Poll found changes push missed for Washer: {'t_power': (0, 1)}" in caplog.text


def _real_appliance() -> SimpleNamespace:
    """An appliance whose status updates like the library's."""
    status: dict = {"Selected_program_id_status": 0, "Curent_program_duration": 202}

    def update_status(properties):
        changed = {k for k, v in properties.items() if status.get(k) != int(v)}
        status.update({k: int(v) for k, v in properties.items()})
        return changed

    return SimpleNamespace(
        device_id="d1", puid="pu1", device_nickname="Dishwasher", status_list=status, update_status=update_status
    )


async def _command(coordinator: ConnectLifeCoordinator, now: float) -> None:
    coordinator.api.update_appliance = AsyncMock()
    with patch("custom_components.connectlife.coordinator.monotonic", return_value=now):
        await coordinator.async_update_device(
            "d1", {"Selected_program_id": 1}, {"Selected_program_id_status": 1}
        )


def _push(coordinator: ConnectLifeCoordinator, now: float, **properties: str) -> None:
    with patch("custom_components.connectlife.coordinator.monotonic", return_value=now):
        coordinator.apply_push_status("pu1", properties)


async def test_push_from_before_a_command_is_ignored() -> None:
    appliance = _real_appliance()
    coordinator = _coordinator(appliance)

    await _command(coordinator, 100)
    _push(coordinator, 101, Selected_program_id_status="0", Curent_program_duration="210")

    # The stale program is ignored, the other property applied.
    assert appliance.status_list == {"Selected_program_id_status": 1, "Curent_program_duration": 210}

    _push(coordinator, 103, Selected_program_id_status="1", Curent_program_duration="131")
    assert appliance.status_list == {"Selected_program_id_status": 1, "Curent_program_duration": 131}
    assert coordinator._commanded == {}

    # Once confirmed, a later change (e.g. on the device) applies at once.
    _push(coordinator, 104, Selected_program_id_status="0")
    assert appliance.status_list["Selected_program_id_status"] == 0


async def test_command_not_confirmed_gives_way_after_settle_time() -> None:
    appliance = _real_appliance()
    coordinator = _coordinator(appliance)

    await _command(coordinator, 100)
    _push(coordinator, 109, Selected_program_id_status="0")
    assert appliance.status_list["Selected_program_id_status"] == 1

    _push(coordinator, 110, Selected_program_id_status="0")
    assert appliance.status_list["Selected_program_id_status"] == 0
    assert coordinator._commanded == {}

