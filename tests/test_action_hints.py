"""Tests for the hints logged by the generic actions."""

from __future__ import annotations

import logging

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from custom_components.connectlife import action_hints
from custom_components.connectlife.action_hints import find_control, log_hints

MAPPING = {
    "climate": {"hvac_modes": [{"hvac_mode": "cool", "modeCool": 1, "modeHeat": 0}]},
    "buttons": [{"key": "start", "write": {"Actions": 2}}],
    "properties": [
        {"property": "t_power", "switch": {}},
        {"property": "holiday_mode", "switch": {"command": {"name": "SET_HOLIDAY_MODE"}}},
        {"property": "t_temp", "climate": {"target": "target_temperature"}},
        {"property": "f_temp_in", "climate": {"target": "current_temperature"}},
        {"property": "f_status", "sensor": {}},
    ],
}


@pytest.fixture(autouse=True)
def _reset_logged():
    action_hints._logged.clear()
    yield
    action_hints._logged.clear()


@pytest.mark.parametrize(
    ("prop", "value", "expected"),
    [
        ("Actions", 2, (Platform.BUTTON, "button-start")),
        ("Actions", 3, None),  # no button sends 3
        ("t_power", 1, (Platform.SWITCH, "t_power")),
        ("SET_HOLIDAY_MODE", 1, (Platform.SWITCH, "holiday_mode")),
        ("holiday_mode", 1, None),  # written through its command, not directly
        ("t_temp", 22, (Platform.CLIMATE, "climate")),
        ("f_temp_in", 22, None),  # read-only climate target
        ("modeCool", 1, (Platform.CLIMATE, "climate")),  # climate value set
        ("f_status", 1, None),
        ("unknown", 1, None),
    ],
)
def test_find_control(build_mapping, prop, value, expected) -> None:
    control = find_control(build_mapping(base=MAPPING), prop, value)
    assert (control[:2] if control else None) == expected


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == action_hints.__name__ and r.levelno == logging.WARNING]


async def test_single_property_with_control_gets_a_hint(hass: HomeAssistant, build_mapping, caplog) -> None:
    log_hints(hass, "connectlife.update", build_mapping(base=MAPPING), "dev", "AC (999-000)", {"t_power": 1})
    assert _warnings(caplog) == ["connectlife.update wrote t_power = 1 on AC (999-000): use t_power instead"]


async def test_unknown_property_asks_for_feedback(hass: HomeAssistant, build_mapping, caplog) -> None:
    log_hints(hass, "connectlife.set_value", build_mapping(base=MAPPING), "dev", "AC (999-000)", {"f_status": 3})
    [message] = _warnings(caplog)
    assert message.startswith("connectlife.set_value wrote f_status = 3 on AC (999-000), which has no control")
    assert action_hints.ISSUES_URL in message


async def test_several_properties_only_feedback(hass: HomeAssistant, build_mapping, caplog) -> None:
    """Writing several properties is deliberate: no hints, but feedback for the unknown ones."""
    log_hints(
        hass, "connectlife.update", build_mapping(base=MAPPING), "dev", "AC (999-000)",
        {"t_power": 1, "unknown": 5},
    )
    [message] = _warnings(caplog)
    assert message.startswith("connectlife.update wrote unknown = 5 (together with 1 other properties) on AC")


async def test_logged_once_per_device_and_property(hass: HomeAssistant, build_mapping, caplog) -> None:
    mapping = build_mapping(base=MAPPING)
    for value in (1, 2):
        log_hints(hass, "connectlife.update", mapping, "dev", "AC (999-000)", {"unknown": value})
    log_hints(hass, "connectlife.update", mapping, "other", "AC 2 (999-000)", {"unknown": 1})
    assert len(_warnings(caplog)) == 2  # once for "dev", once for "other"


async def test_buttons_logged_once_per_value(hass: HomeAssistant, build_mapping, caplog) -> None:
    """For buttons, the value decides the control, so each value gets its own hint."""
    mapping = build_mapping(base=MAPPING)
    for value in (2, 2, 3):
        log_hints(hass, "connectlife.set_action", mapping, "dev", "Washer (999-000)", {"Actions": value})
    messages = _warnings(caplog)
    assert messages[0] == "connectlife.set_action wrote Actions = 2 on Washer (999-000): use start instead"
    assert messages[1].startswith("connectlife.set_action wrote Actions = 3 on Washer (999-000), which has no control")
    assert len(messages) == 2
