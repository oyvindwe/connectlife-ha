"""Tests for the ConnectLife coordinator."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.connectlife.coordinator import ConnectLifeCoordinator


def _coordinator() -> tuple[ConnectLifeCoordinator, MagicMock]:
    coordinator = ConnectLifeCoordinator.__new__(ConnectLifeCoordinator)
    coordinator.data = None  # type: ignore[assignment]
    coordinator._update_unavailable_device_issues = MagicMock()
    # Devices registered in Home Assistant; tests add or remove IDs as needed.
    coordinator._registered_device_ids = MagicMock(return_value={"a", "b"})
    coordinator.api = SimpleNamespace(get_appliances=AsyncMock(), appliances=[])
    coordinator.error_count = 0
    coordinator._setup_device_ids = None
    schedule_reload = MagicMock()
    coordinator.hass = SimpleNamespace(data={}, config_entries=SimpleNamespace(async_schedule_reload=schedule_reload))
    coordinator.config_entry = SimpleNamespace(entry_id="entry-1")
    return coordinator, schedule_reload


async def _poll(coordinator: ConnectLifeCoordinator, *device_ids: str):
    coordinator.api.appliances = [SimpleNamespace(device_id=d) for d in device_ids]
    with patch("custom_components.connectlife.coordinator.terms_accepted"):
        # DataUpdateCoordinator stores the result as `data` after each refresh.
        coordinator.data = await coordinator._async_update_data()
    return coordinator.data


async def test_new_device_schedules_one_reload() -> None:
    coordinator, schedule_reload = _coordinator()

    await _poll(coordinator, "a")
    await _poll(coordinator, "a")
    schedule_reload.assert_not_called()

    data = await _poll(coordinator, "a", "b")
    assert set(data) == {"a", "b"}
    schedule_reload.assert_called_once_with("entry-1")

    await _poll(coordinator, "a", "b")
    schedule_reload.assert_called_once()


async def test_removed_device_does_not_reload() -> None:
    coordinator, schedule_reload = _coordinator()

    await _poll(coordinator, "a", "b")
    await _poll(coordinator, "a")
    await _poll(coordinator, "a", "b")

    schedule_reload.assert_not_called()


async def test_changed_device_list_updates_unavailable_device_issues() -> None:
    coordinator, _ = _coordinator()
    update_issues = coordinator._update_unavailable_device_issues

    await _poll(coordinator, "a", "b")
    await _poll(coordinator, "a", "b")
    update_issues.assert_not_called()

    await _poll(coordinator, "a")
    update_issues.assert_called_once()
    assert set(update_issues.call_args.args[0]) == {"a"}

    await _poll(coordinator, "a", "b")
    assert update_issues.call_count == 2
    assert set(update_issues.call_args.args[0]) == {"a", "b"}


async def test_returning_device_deleted_in_home_assistant_schedules_reload() -> None:
    coordinator, schedule_reload = _coordinator()

    await _poll(coordinator, "a", "b")
    await _poll(coordinator, "a")
    # The user deleted "b" (e.g. from its repair) while it was missing.
    coordinator._registered_device_ids.return_value = {"a"}
    await _poll(coordinator, "a", "b")

    schedule_reload.assert_called_once_with("entry-1")
