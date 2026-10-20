"""Tests for the ConnectLife coordinator."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import dataclasses
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.connectlife.const import DOMAIN
from custom_components.connectlife.coordinator import (
    MAX_RETRIES,
    UNAVAILABLE_DEVICE_GRACE_PERIOD,
    ConnectLifeCoordinator,
)


def _coordinator() -> tuple[ConnectLifeCoordinator, MagicMock]:
    coordinator = ConnectLifeCoordinator.__new__(ConnectLifeCoordinator)
    coordinator.data = None  # type: ignore[assignment]
    coordinator._update_unavailable_device_issues = MagicMock()
    # Devices registered in Home Assistant; tests add or remove IDs as needed.
    coordinator._registered_devices = MagicMock(return_value=dict.fromkeys(("a", "b")))
    coordinator.api = SimpleNamespace(get_appliances=AsyncMock(), appliances=[])
    coordinator.error_count = 0
    coordinator._setup_device_ids = None
    coordinator._missing_polls = {}
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


async def test_every_poll_after_setup_updates_unavailable_device_issues() -> None:
    coordinator, _ = _coordinator()
    update_issues = coordinator._update_unavailable_device_issues

    await _poll(coordinator, "a", "b")
    # Setup starts tracking missing devices via cleanup_removed_entities.
    update_issues.assert_not_called()

    await _poll(coordinator, "a", "b")
    assert set(update_issues.call_args.args[0]) == {"a", "b"}

    await _poll(coordinator, "a")
    assert set(update_issues.call_args.args[0]) == {"a"}
    assert update_issues.call_count == 2


async def test_missing_device_keeps_last_known_state_for_max_retries_polls() -> None:
    coordinator, schedule_reload = _coordinator()

    first = await _poll(coordinator, "a", "b")
    for _ in range(MAX_RETRIES - 1):
        data = await _poll(coordinator, "a")
        assert data["b"] is first["b"]

    data = await _poll(coordinator, "a")
    assert set(data) == {"a"}

    # Back, and missing again: keeps the new state, counting from scratch.
    second = await _poll(coordinator, "a", "b")
    for _ in range(MAX_RETRIES - 1):
        data = await _poll(coordinator, "a")
        assert data["b"] is second["b"]
    schedule_reload.assert_not_called()


async def test_returning_device_deleted_in_home_assistant_schedules_reload() -> None:
    coordinator, schedule_reload = _coordinator()

    await _poll(coordinator, "a", "b")
    for _ in range(MAX_RETRIES):
        await _poll(coordinator, "a")
    # The user deleted "b" (e.g. from its repair) while it was missing.
    coordinator._registered_devices.return_value = dict.fromkeys(("a",))
    await _poll(coordinator, "a", "b")

    schedule_reload.assert_called_once_with("entry-1")


async def test_unavailable_device_issue_after_grace_period(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    device_reg = dr.async_get(hass)
    for device_id in ("a", "b"):
        device_reg.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, device_id)}, name=device_id
        )
    coordinator = ConnectLifeCoordinator.__new__(ConnectLifeCoordinator)
    coordinator.hass = hass
    coordinator.config_entry = entry
    coordinator._missing_since = {}
    issue_reg = ir.async_get(hass)
    start = 1000.0

    def update(at: timedelta, *device_ids: str) -> set[str]:
        """Return the devices with an issue."""
        with patch("custom_components.connectlife.coordinator.monotonic", return_value=start + at.total_seconds()):
            coordinator._update_unavailable_device_issues(device_ids)
        return {
            issue_id.removeprefix("unavailable_device.")
            for (domain, issue_id) in issue_reg.issues
            if domain == DOMAIN
        }

    # A single short device list does not raise an issue.
    assert update(timedelta(), "a") == set()
    assert update(timedelta(minutes=1), "a", "b") == set()

    # Missing again: the grace period starts over.
    assert update(timedelta(minutes=2), "a") == set()
    assert update(UNAVAILABLE_DEVICE_GRACE_PERIOD + timedelta(minutes=1), "a") == set()
    assert update(UNAVAILABLE_DEVICE_GRACE_PERIOD + timedelta(minutes=2), "a") == {"b"}

    # Back again clears the issue.
    assert update(UNAVAILABLE_DEVICE_GRACE_PERIOD + timedelta(minutes=3), "a", "b") == set()


async def test_inactive_unavailable_device_issue_is_created_again(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "a")}, name="a"
    )
    coordinator = ConnectLifeCoordinator.__new__(ConnectLifeCoordinator)
    coordinator.hass = hass
    coordinator.config_entry = entry
    # Missing since well before the grace period.
    coordinator._missing_since = {"a": -UNAVAILABLE_DEVICE_GRACE_PERIOD.total_seconds()}
    issue_reg = ir.async_get(hass)
    key = (DOMAIN, "unavailable_device.a")
    coordinator._update_unavailable_device_issues(())
    # Simulate the issue restored inactive after a restart.
    issue_reg.issues[key] = dataclasses.replace(issue_reg.issues[key], active=False)

    with patch("custom_components.connectlife.coordinator._LOGGER") as logger:
        coordinator._update_unavailable_device_issues(())
        coordinator._update_unavailable_device_issues(())

    assert issue_reg.issues[key].active
    logger.warning.assert_called_once()
