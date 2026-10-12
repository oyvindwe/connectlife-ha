"""Tests for the ConnectLife base entity."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from custom_components.connectlife.climate import ConnectLifeClimate


async def test_disable_beep_does_not_change_preset() -> None:
    climate = ConnectLifeClimate.__new__(ConnectLifeClimate)
    climate.device_id = "device"
    climate._disable_beep = True
    climate.preset_map = {"eco": {"t_eco": 1, "t_power": 1}}
    commands: list[dict] = []

    async def async_update_device(device_id, command, properties) -> None:
        commands.append(dict(command))

    climate.coordinator = SimpleNamespace(async_update_device=async_update_device, hass=None)

    with patch("custom_components.connectlife.entity.ir.async_delete_issue"):
        await climate.async_set_preset_mode("eco")

    assert commands == [{"t_eco": 1, "t_power": 1, "t_beep": 0}]
    assert climate.preset_map["eco"] == {"t_eco": 1, "t_power": 1}
