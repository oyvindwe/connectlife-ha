"""Tests for ConnectLife climate mode mapping."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.climate import ClimateEntityFeature, HVACMode

from custom_components.connectlife.climate import (
    ConnectLifeClimate,
    _add_hvac_mode_mapping,
    is_climate,
)
from custom_components.connectlife.const import HVAC_MODE, IS_ON
from custom_components.connectlife.dictionaries import Dictionary, Property


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


def test_disabled_climate_property_is_not_exposed() -> None:
    """A climate-mapped property with `disable: true` must be dropped.

    Regression test: the climate platform previously only checked
    `hasattr(prop, climate)` and ignored `disable`, so a disabled swing axis
    still leaked onto the entity. (A ducted AC variant relies on this to
    suppress the swing controls inherited from its base mapping.)
    """
    dictionary = Dictionary(
        climate=None,
        properties={
            "t_power": Property(
                {"property": "t_power", "climate": {"target": "is_on"}}
            ),
            "t_swing_angle": Property(
                {
                    "property": "t_swing_angle",
                    "disable": True,
                    "climate": {
                        "target": "swing_mode",
                        "options": {0: "off", 1: "on"},
                    },
                }
            ),
        },
        buttons=[],
    )

    # Still a climate device (t_power is enabled) ...
    assert is_climate(dictionary)

    appliance = SimpleNamespace(
        device_id="dev1",
        device_nickname="Duct AC",
        device_feature_name="ducted",
        device_type_code="009",
        device_feature_code="19901",
        room_name="Living Room",
        status_list={"t_power": 0, "t_swing_angle": 0},
    )
    coordinator = SimpleNamespace(
        data={appliance.device_id: appliance},
        config_entry=SimpleNamespace(options={}, entry_id="e"),
        hass=None,
        last_update_success=True,
        add_entity=lambda *a, **k: None,
    )
    climate = ConnectLifeClimate(coordinator, appliance, dictionary)

    # ... but the disabled swing axis is not exposed.
    assert "swing_mode" not in climate.target_map
    assert not climate._attr_supported_features & ClimateEntityFeature.SWING_MODE
