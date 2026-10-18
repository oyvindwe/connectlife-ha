"""Tests for the ConnectLife base entity."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from connectlife.api import LifeConnectError
from homeassistant.exceptions import ServiceValidationError

from custom_components.connectlife.button import ConnectLifeButton
from custom_components.connectlife.climate import ConnectLifeClimate
from custom_components.connectlife.dictionaries import Button
from custom_components.connectlife.switch import ConnectLifeSwitch


def _coordinator(commands: list[dict], status_list: dict | None = None) -> SimpleNamespace:
    """A coordinator recording the commands sent, for a device using the 999-000 test dictionary."""

    async def async_update_device(device_id, command, properties) -> None:
        commands.append({"command": dict(command), "properties": dict(properties)})

    appliance = SimpleNamespace(
        device_type_code="999",
        device_feature_code="000",
        device_nickname="test",
        status_list=status_list or {},
    )
    return SimpleNamespace(
        async_update_device=async_update_device,
        data={"device": appliance},
        hass=None,
    )


async def test_disable_beep_does_not_change_preset(build_dictionary) -> None:
    build_dictionary(base={"properties": []})
    climate = ConnectLifeClimate.__new__(ConnectLifeClimate)
    climate.device_id = "device"
    climate._disable_beep = True
    climate.preset_map = {"eco": {"t_eco": 1, "t_power": 1}}
    commands: list[dict] = []
    climate.coordinator = _coordinator(commands)

    with patch("custom_components.connectlife.entity.ir.async_delete_issue"):
        await climate.async_set_preset_mode("eco")

    assert [c["command"] for c in commands] == [{"t_eco": 1, "t_power": 1, "t_beep": 0}]
    assert climate.preset_map["eco"] == {"t_eco": 1, "t_power": 1}


async def test_property_include_is_sent_with_command(build_dictionary) -> None:
    build_dictionary(base={"properties": [
        {"property": "t_power", "include": ["t_fan_mute"], "climate": {"target": "is_on"}},
        {"property": "t_fan_mute", "switch": {}},
    ]})
    climate = ConnectLifeClimate.__new__(ConnectLifeClimate)
    climate.device_id = "device"
    climate._disable_beep = False
    commands: list[dict] = []
    climate.coordinator = _coordinator(commands, {"t_power": 0, "t_fan_mute": 1})
    command = {"t_power": 1}

    await climate.async_update_device(command)

    assert commands == [{"command": {"t_power": 1, "t_fan_mute": 1}, "properties": {"t_power": 1}}]
    assert command == {"t_power": 1}


async def test_button_include_is_sent_with_write(build_dictionary) -> None:
    build_dictionary(base={"properties": [
        {"property": "Program_status", "select": {
            "options": {0: "eco", 9: "sportswear"},
            "command": {"name": "Program"},
        }},
        {"property": "Temperature_status", "unavailable": 0, "select": {
            "options": {1: "cold", 4: "40_c"},
            "command": {"name": "Temperature", "adjust": 1},
        }},
        {"property": "Spin_status", "unavailable": 0, "select": {
            "options": {1: "0_rpm", 8: "1200_rpm"},
            "command": {"name": "Spin", "adjust": 1},
        }},
    ]})
    button = ConnectLifeButton.__new__(ConnectLifeButton)
    button.device_id = "device"
    button._disable_beep = False
    button.button = Button({
        "key": "start",
        "include": ["Program_status", "Temperature_status", "Spin_status"],
        "write": {"Actions": 1},
    })
    commands: list[dict] = []
    # The program has no temperature option, so its temperature is unavailable.
    button.coordinator = _coordinator(commands, {"Program_status": 9, "Temperature_status": 0, "Spin_status": 8})

    await button.async_press()

    assert commands == [{"command": {"Actions": 1, "Program": 9, "Spin": 7}, "properties": {}}]
    assert button.button.write == {"Actions": 1}


MUTEX_ERROR = "Unexpected response from HijuConn gateway: code=160001 description='Command status mutex'"


async def test_command_rejected_raises_readable_error() -> None:
    climate = ConnectLifeClimate.__new__(ConnectLifeClimate)
    climate.device_id = "device"
    climate._disable_beep = False

    async def async_update_device(device_id, command, properties) -> None:
        raise LifeConnectError(MUTEX_ERROR)

    climate.coordinator = SimpleNamespace(async_update_device=async_update_device, hass=None, data={})

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

    climate.coordinator = SimpleNamespace(async_update_device=async_update_device, hass=None, data={})

    with pytest.raises(ServiceValidationError):
        await climate.async_update_device({"t_super": 1})

    assert commands == [{"t_super": 1, "t_beep": 0}]
    assert climate._disable_beep_failure_count == 0
    assert climate._disable_beep


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
