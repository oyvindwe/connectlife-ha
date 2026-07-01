"""Tests for ConnectLife climate mode mapping."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.climate import ClimateEntityFeature, HVACMode

from custom_components.connectlife.climate import (
    ConnectLifeClimate,
    _add_hvac_mode_mapping,
    is_climate,
)
from custom_components.connectlife.const import (
    CONF_DEVICES,
    CONF_TARGET_OVERRIDES,
    HVAC_MODE,
    IS_ON,
    SWING_MODE,
)
from custom_components.connectlife.dictionaries import Dictionary, Property
from custom_components.connectlife.utils import (
    climate_bound_properties,
    contested_climate_targets,
)


def _coordinator(appliance: SimpleNamespace, options: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        data={appliance.device_id: appliance},
        config_entry=SimpleNamespace(options=options or {}, entry_id="e"),
        hass=None,
        last_update_success=True,
        add_entity=lambda *a, **k: None,
    )


def _override_options(device_id: str, target: str, property_name: str) -> dict:
    return {CONF_DEVICES: {device_id: {CONF_TARGET_OVERRIDES: {target: property_name}}}}


def _swing_dictionary() -> Dictionary:
    """t_swing_angle (priority 1) and t_up_down (switch + priority 2) both
    claim swing_mode, mirroring the hoisted 009.yaml mapping."""
    return Dictionary(
        climate=None,
        properties={
            "t_power": Property(
                {"property": "t_power", "climate": {"target": "is_on"}}
            ),
            "t_swing_angle": Property(
                {
                    "property": "t_swing_angle",
                    "climate": {
                        "target": "swing_mode",
                        "priority": 1,
                        "options": {0: "swing", 1: "auto"},
                    },
                }
            ),
            "t_up_down": Property(
                {
                    "property": "t_up_down",
                    "switch": {"device_class": "switch"},
                    "climate": {
                        "target": "swing_mode",
                        "priority": 2,
                        "options": {0: "off", 1: "on"},
                    },
                }
            ),
        },
        buttons=[],
    )


def _swing_appliance(status_list: dict[str, int]) -> SimpleNamespace:
    return SimpleNamespace(
        device_id="dev1",
        device_nickname="AC",
        device_feature_name="104",
        device_type_code="009",
        device_feature_code="104",
        room_name="Kitchen",
        status_list=status_list,
    )


def test_swing_mode_prefers_higher_priority_candidate() -> None:
    """When both axes are exposed, the lower-priority number (t_swing_angle)
    wins swing_mode and t_up_down falls back to its switch (issue #590)."""
    dictionary = _swing_dictionary()
    appliance = _swing_appliance({"t_power": 1, "t_swing_angle": 0, "t_up_down": 0})
    climate = ConnectLifeClimate(_coordinator(appliance), appliance, dictionary)

    assert climate.target_map[SWING_MODE] == "t_swing_angle"
    # t_up_down lost swing_mode, so it must remain available to the switch platform.
    assert climate_bound_properties(appliance, dictionary) == {"t_swing_angle", "t_power"}


def test_swing_mode_falls_back_to_lower_priority_candidate() -> None:
    """A device exposing only t_up_down promotes it to swing_mode."""
    dictionary = _swing_dictionary()
    appliance = _swing_appliance({"t_power": 1, "t_up_down": 0})
    climate = ConnectLifeClimate(_coordinator(appliance), appliance, dictionary)

    assert climate.target_map[SWING_MODE] == "t_up_down"
    assert "t_up_down" in climate_bound_properties(appliance, dictionary)


def test_swing_mode_override_pins_configured_property() -> None:
    """A per-device override pins t_up_down as swing_mode even when the
    higher-priority t_swing_angle is also exposed (issue #607)."""
    dictionary = _swing_dictionary()
    appliance = _swing_appliance({"t_power": 1, "t_swing_angle": 0, "t_up_down": 0})
    options = _override_options(appliance.device_id, SWING_MODE, "t_up_down")
    climate = ConnectLifeClimate(_coordinator(appliance, options), appliance, dictionary)

    assert climate.target_map[SWING_MODE] == "t_up_down"
    # t_up_down now wins swing_mode, so it is no longer offered as a switch.
    overrides = options[CONF_DEVICES][appliance.device_id][CONF_TARGET_OVERRIDES]
    bound = climate_bound_properties(appliance, dictionary, overrides)
    assert bound == {"t_up_down", "t_power"}


def test_swing_mode_override_ignored_when_property_absent() -> None:
    """An override naming a property the device doesn't expose is ignored,
    falling back to the automatic priority-based winner."""
    dictionary = _swing_dictionary()
    appliance = _swing_appliance({"t_power": 1, "t_swing_angle": 0, "t_up_down": 0})
    options = _override_options(appliance.device_id, SWING_MODE, "t_not_present")
    climate = ConnectLifeClimate(_coordinator(appliance, options), appliance, dictionary)

    assert climate.target_map[SWING_MODE] == "t_swing_angle"


def test_contested_targets_reports_only_multi_candidate_targets() -> None:
    """contested_climate_targets lists a target only when the device exposes
    more than one candidate for it — that's what the options flow offers."""
    dictionary = _swing_dictionary()

    both = _swing_appliance({"t_power": 1, "t_swing_angle": 0, "t_up_down": 0})
    assert contested_climate_targets(both, dictionary) == {
        SWING_MODE: ["t_swing_angle", "t_up_down"]
    }

    single = _swing_appliance({"t_power": 1, "t_up_down": 0})
    assert contested_climate_targets(single, dictionary) == {}


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
