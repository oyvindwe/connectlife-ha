"""Tests for the ConnectLife coordinator."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.connectlife.coordinator import ConnectLifeCoordinator


def _coordinator() -> tuple[ConnectLifeCoordinator, MagicMock]:
    coordinator = ConnectLifeCoordinator.__new__(ConnectLifeCoordinator)
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
        return await coordinator._async_update_data()


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
