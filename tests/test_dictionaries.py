"""Tests for the property inheritance merge in dictionaries.py."""

from __future__ import annotations

from custom_components.connectlife.dictionaries import (
    Property,
    Sensor,
    _merge_property,
)


def test_override_with_no_platform_inherits_everything():
    base = {
        "property": "t_temp",
        "icon": "mdi:thermometer",
        "climate": {
            "target": "target_temperature",
            "min_value": 16,
            "max_value": 32,
        },
    }
    override = {"property": "t_temp"}

    merged = _merge_property(base, override)

    assert merged == base


def test_same_platform_merges_field_by_field():
    base = {
        "property": "t_temp",
        "climate": {
            "target": "target_temperature",
            "min_value": 16,
            "max_value": 32,
        },
    }
    override = {
        "property": "t_temp",
        "climate": {"max_value": 30},
    }

    merged = _merge_property(base, override)

    assert merged == {
        "property": "t_temp",
        "climate": {
            "target": "target_temperature",
            "min_value": 16,
            "max_value": 30,
        },
    }


def test_options_replace_as_whole():
    base = {
        "property": "t_work_mode",
        "climate": {
            "target": "hvac_mode",
            "options": {0: "fan_only", 1: "heat", 2: "cool", 3: "dry", 4: "auto"},
        },
    }
    override = {
        "property": "t_work_mode",
        "climate": {"options": {0: "fan_only", 2: "cool", 3: "dry", 4: "auto"}},
    }

    merged = _merge_property(base, override)

    assert merged["climate"]["target"] == "hvac_mode"
    assert merged["climate"]["options"] == {
        0: "fan_only",
        2: "cool",
        3: "dry",
        4: "auto",
    }


def test_combine_replaces_as_whole():
    base = {
        "property": "total_energy",
        "combine": [{"property": "a"}, {"property": "b"}],
    }
    override = {
        "property": "total_energy",
        "combine": [{"property": "c"}],
    }

    merged = _merge_property(base, override)

    assert merged["combine"] == [{"property": "c"}]


def test_dict_valued_min_max_replace_as_whole():
    base = {
        "property": "t_temp",
        "climate": {
            "target": "target_temperature",
            "min_value": {"celsius": 16, "fahrenheit": 61},
            "max_value": {"celsius": 32, "fahrenheit": 90},
        },
    }
    override = {
        "property": "t_temp",
        "climate": {"min_value": {"celsius": 8, "fahrenheit": 46}},
    }

    merged = _merge_property(base, override)

    assert merged["climate"]["min_value"] == {"celsius": 8, "fahrenheit": 46}
    assert merged["climate"]["max_value"] == {"celsius": 32, "fahrenheit": 90}


def test_different_platform_replaces_block_but_top_level_inherits():
    base = {
        "property": "p",
        "icon": "mdi:eye",
        "hide": True,
        "sensor": {"device_class": "temperature", "unit": "°C"},
    }
    override = {
        "property": "p",
        "select": {"options": {0: "a", 1: "b"}},
    }

    merged = _merge_property(base, override)

    assert merged["icon"] == "mdi:eye"
    assert merged["hide"] is True
    assert "sensor" not in merged
    assert merged["select"] == {"options": {0: "a", 1: "b"}}


def test_explicit_null_in_platform_unsets_base_field():
    base = {
        "property": "t_setpoint",
        "sensor": {
            "device_class": "temperature",
            "unit": "°C",
            "state_class": "measurement",
        },
    }
    override = {
        "property": "t_setpoint",
        "sensor": {"state_class": None},
    }

    merged = _merge_property(base, override)

    assert merged["sensor"]["device_class"] == "temperature"
    assert merged["sensor"]["unit"] == "°C"
    assert merged["sensor"]["state_class"] is None


def test_explicit_null_at_top_level_unsets_field():
    base = {
        "property": "p",
        "icon": "mdi:eye",
        "sensor": {"device_class": "temperature", "unit": "°C"},
    }
    override = {
        "property": "p",
        "icon": None,
    }

    merged = _merge_property(base, override)

    assert merged["icon"] is None
    assert merged["sensor"] == {"device_class": "temperature", "unit": "°C"}


def test_bare_platform_in_subtype_inherits_base_block():
    """A subtype writing ``switch:`` (parsed as None) is YAML shorthand for
    ``switch: {}`` — "this property is a switch with no overrides" — and
    should inherit the base's switch block, not unset the platform."""
    base = {
        "property": "AntiCrease",
        "icon": "mdi:iron",
        "switch": {"on": 1, "off": 0},
    }
    override = {
        "property": "AntiCrease",
        "icon": "mdi:iron",
        "switch": None,
    }

    merged = _merge_property(base, override)

    assert merged["switch"] == {"on": 1, "off": 0}


def test_bare_platform_in_subtype_with_no_base_platform():
    """When base has no platform key, a subtype's bare ``switch:`` adds the
    platform; the value flows through as None and the parser handles it as
    "switch entity with defaults"."""
    base = {"property": "p"}
    override = {"property": "p", "switch": None}

    merged = _merge_property(base, override)

    assert "switch" in merged
    assert merged["switch"] is None


def test_no_base_returns_override_copy():
    override = {"property": "p", "sensor": {"unit": "kWh"}}

    merged = _merge_property(None, override)

    assert merged == override
    assert merged is not override


def test_property_constructed_from_merged_dict():
    base = {
        "property": "t_temp",
        "climate": {
            "target": "target_temperature",
            "max_value": 32,
            "min_value": 16,
        },
    }
    override = {
        "property": "t_temp",
        "climate": {"max_value": 30},
    }

    merged = _merge_property(base, override)
    prop = Property(merged)

    assert prop.climate.target == "target_temperature"
    assert prop.climate.max_value == 30
    assert prop.climate.min_value == 16


def test_unknown_value_zero_is_honored():
    """`unknown_value: 0` should be preserved as 0, not silently dropped.
    A device reporting 0 (e.g., probe removed, sensor off) means "unknown",
    and the YAML author signals that with the explicit 0 sentinel."""
    sensor = Sensor("oven_temperature", {"unknown_value": 0})
    assert sensor.unknown_value == 0


def test_unknown_value_null_is_none():
    sensor = Sensor("p", {"unknown_value": None})
    assert sensor.unknown_value is None


def test_unknown_value_absent_is_none():
    sensor = Sensor("p", {})
    assert sensor.unknown_value is None


def test_hide_false_actually_disables_hiding():
    """Regression: the parser used `entry[HIDE] == bool(entry[HIDE])`, which
    evaluates True for any boolean — so `hide: false` previously set
    `self.hide = True`. With inheritance, that broke the only way for a
    subtype to clear an inherited `hide: true` from a base placeholder."""
    assert Property({"property": "p", "hide": False}).hide is False
    assert Property({"property": "p", "hide": True}).hide is True
    assert Property({"property": "p"}).hide is False


def test_disable_false_actually_disables_disabling():
    assert Property({"property": "p", "disable": False}).disable is False
    assert Property({"property": "p", "disable": True}).disable is True
    assert Property({"property": "p"}).disable is False
