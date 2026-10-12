"""Tests for the ConnectLife base entity."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from connectlife.api import LifeConnectError
from homeassistant.exceptions import ServiceValidationError

from custom_components.connectlife.climate import ConnectLifeClimate
from custom_components.connectlife.switch import ConnectLifeSwitch


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


MUTEX_ERROR = "Unexpected response from HijuConn gateway: code=160001 description='Command status mutex'"


async def test_command_rejected_raises_readable_error() -> None:
    climate = ConnectLifeClimate.__new__(ConnectLifeClimate)
    climate.device_id = "device"
    climate._disable_beep = False

    async def async_update_device(device_id, command, properties) -> None:
        raise LifeConnectError(MUTEX_ERROR)

    climate.coordinator = SimpleNamespace(async_update_device=async_update_device, hass=None)

    with pytest.raises(ServiceValidationError) as exc_info:
        await climate.async_update_device({"t_super": 1})

    assert exc_info.value.translation_key == "command_rejected"


async def test_command_rejected_is_not_a_beep_failure() -> None:
    climate = ConnectLifeClimate.__new__(ConnectLifeClimate)
    climate.device_id = "device"
    climate._disable_beep = True
    climate._disable_beep_failure_count = 0
    commands: list[dict] = []

    async def async_update_device(device_id, command, properties) -> None:
        commands.append(dict(command))
        raise LifeConnectError(MUTEX_ERROR)

    climate.coordinator = SimpleNamespace(async_update_device=async_update_device, hass=None)

    with pytest.raises(ServiceValidationError):
        await climate.async_update_device({"t_super": 1})

    assert commands == [{"t_super": 1, "t_beep": 0}]
    assert climate._disable_beep_failure_count == 0
    assert climate._disable_beep


def test_available_when_gates_entity() -> None:
    switch = ConnectLifeSwitch.__new__(ConnectLifeSwitch)
    switch.device_id = "device"
    switch._expose_offline_state = False
    switch._unavailable_status = "t_super"
    switch._unavailable_value = None
    switch._available_when = {"t_power": [1], "t_work_mode": [1, 2]}
    appliance = SimpleNamespace(offline_state=1, status_list={"t_super": 0, "t_power": 1, "t_work_mode": 2})
    switch.coordinator = SimpleNamespace(last_update_success=True, data={"device": appliance})

    assert switch.available
    appliance.status_list["t_work_mode"] = 4
    assert not switch.available
    appliance.status_list["t_work_mode"] = 1
    appliance.status_list["t_power"] = 0
    assert not switch.available


def test_update_for_device_missing_from_data_writes_unavailable_state() -> None:
    switch = ConnectLifeSwitch.__new__(ConnectLifeSwitch)
    switch.device_id = "gone"
    switch.status = "t_super"
    switch._expose_offline_state = False
    switch._unavailable_status = "t_super"
    switch._unavailable_value = None
    switch._available_when = {}
    switch.coordinator = SimpleNamespace(last_update_success=True, data={"other": None})

    with patch.object(ConnectLifeSwitch, "async_write_ha_state") as write:
        switch._handle_coordinator_update()

    write.assert_called_once()
    assert not switch.available
