"""Tests for ConnectLife climate mode mapping."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.climate import ClimateEntityFeature, HVACMode

from custom_components.connectlife.climate import (
    ConnectLifeClimate,
    _add_hvac_mode_mapping,
)
from custom_components.connectlife.const import HVAC_MODE, IS_ON
from custom_components.connectlife.dictionaries import Dictionaries


def test_hvac_mode_alias_does_not_override_canonical_reverse_mapping() -> None:
    hvac_modes: list[HVACMode] = []
    hvac_mode_map: dict[int, HVACMode] = {}
    hvac_mode_reverse_map: dict[HVACMode, int] = {}

    _add_hvac_mode_mapping(5, "eco", hvac_modes, hvac_mode_map, hvac_mode_reverse_map)

    assert hvac_mode_map[5] == HVACMode.COOL
    assert hvac_modes == []
    assert hvac_mode_reverse_map == {}

    _add_hvac_mode_mapping(2, "cool", hvac_modes, hvac_mode_map, hvac_mode_reverse_map)

    assert hvac_mode_map[5] == HVACMode.COOL
    assert hvac_mode_map[2] == HVACMode.COOL
    assert hvac_modes == [HVACMode.COOL]
    assert hvac_mode_reverse_map == {HVACMode.COOL: 2}


async def test_set_hvac_mode_writes_canonical_cool_value() -> None:
    climate = ConnectLifeClimate.__new__(ConnectLifeClimate)
    climate.target_map = {
        HVAC_MODE: "t_work_mode",
        IS_ON: "t_power",
    }
    climate.hvac_mode_reverse_map = {HVACMode.COOL: 2}
    climate._attr_supported_features = ClimateEntityFeature.TURN_ON
    requests: list[dict[str, int]] = []

    async def async_update_device(request: dict[str, int]) -> None:
        requests.append(request)

    climate.async_update_device = async_update_device
    climate.add_target_temperature = lambda request: request

    await climate.async_set_hvac_mode(HVACMode.COOL)

    assert requests == [{"t_power": 1, "t_work_mode": 2}]


def test_008_399_eco_preset_writes_raw_eco_mode() -> None:
    Dictionaries.dictionaries.pop("008-399", None)
    appliance = SimpleNamespace(
        device_type_code="008",
        device_feature_code="399",
        device_nickname="Ultraslim AC",
    )

    dictionary = Dictionaries.get_dictionary(appliance)

    assert {
        "preset": "eco",
        "t_power": 1,
        "t_work_mode": 5,
    } in dictionary.climate["presets"]
