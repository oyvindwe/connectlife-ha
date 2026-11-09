"""Hints logged when the generic ConnectLife actions write properties.

The actions `connectlife.set_action`, `connectlife.update` and `connectlife.set_value` write raw properties. That is
how users reach things the integration doesn't expose yet, and how we learn which controls are missing. So when an
action is used, we log a warning that either:

- points to the existing control that does the same (a "hint"), or
- asks the user to report what the property does, so a control can be added ("feedback").

Logging rules:
- Each message is logged once per device and property (and value, for buttons) per Home Assistant run, so
  automations that call an action regularly don't flood the log.
- Hints are only given when a single property is written. Several properties written together are deliberate (e.g.
  program and options sent with start), which separate entities can't do, so suggesting them would be wrong.
- Feedback is given for every written property without any control, also when written together with others: an
  unknown property is worth reporting whatever it's sent with.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .device_mappings import DeviceMapping
from .utils import has_platform

_LOGGER = logging.getLogger(__name__)

ISSUES_URL = "https://github.com/oyvindwe/connectlife-ha/issues"

# Climate, humidifier and water heater targets that are written (the others are read-only).
WRITABLE_TARGETS = {
    Platform.CLIMATE: {"is_on", "target_temperature", "target_humidity", "hvac_mode", "fan_mode", "swing_mode",
                       "swing_horizontal_mode", "target_temperature_high", "target_temperature_low"},
    Platform.HUMIDIFIER: {"is_on", "target_humidity", "mode"},
    Platform.WATER_HEATER: {"is_on", "target_temperature", "current_operation", "is_away_mode_on"},
}
# The entity name used in the unique ID of the device-level entities (see their constructors).
DEVICE_ENTITY_NAMES = {Platform.CLIMATE: "climate", Platform.HUMIDIFIER: "humidifier",
                       Platform.WATER_HEATER: "waterheater"}

# (device_id, property, value) already logged in this run; value is None unless it decides the control (buttons).
_logged: set[tuple[str, str, Any]] = set()


def find_control(mapping: DeviceMapping, prop: str, value: Any) -> tuple[Platform, str, str] | None:
    """Return (platform, unique ID suffix, label) of the control that writes `prop`, or None.

    A write to `prop` matches a control when:
    - a button writes exactly `prop` = `value` (for buttons the value decides which one, e.g. Actions 2 = start);
    - `prop` is a switch, select or number, or the `command` property another one writes through
      (e.g. SET_HOLIDAY_MODE for holiday_mode);
    - `prop` is a writable climate, humidifier or water heater target, or part of a climate value set or preset.
    For the others the value is ignored: a control exists, even if it offers other values.
    """
    for button in mapping.buttons:
        if button.write == {prop: value}:
            return Platform.BUTTON, f"button-{button.key}", button.key.replace("_", " ")
    for name, entry in mapping.properties.items():
        if entry.disable:
            continue
        for platform in (Platform.SWITCH, Platform.SELECT, Platform.NUMBER):
            if has_platform(platform, entry):
                command = getattr(getattr(entry, platform.value), "command_name", None)
                if (command or name) == prop:
                    return platform, name, name
        for platform, targets in WRITABLE_TARGETS.items():
            if name == prop and has_platform(platform, entry) and getattr(entry, platform.value).target in targets:
                return platform, DEVICE_ENTITY_NAMES[platform], platform.value
    for value_sets in (mapping.hvac_modes, mapping.fan_modes, mapping.presets):
        if any(prop in values for values in value_sets.values()):
            return Platform.CLIMATE, DEVICE_ENTITY_NAMES[Platform.CLIMATE], Platform.CLIMATE.value
    return None


def _entity_id(hass: HomeAssistant, device_id: str, control: tuple[Platform, str, str]) -> str:
    """The control's entity ID, or its label if it isn't registered."""
    platform, suffix, label = control
    entity_id = er.async_get(hass).async_get_entity_id(platform.value, DOMAIN, f"{device_id}-{suffix}")
    return entity_id or label


def log_hints(
    hass: HomeAssistant,
    action: str,
    mapping: DeviceMapping,
    device_id: str,
    device: str,
    data: dict[str, Any],
) -> None:
    """Log a hint or feedback request for each property `action` wrote to `device` (see the module docstring)."""
    single = len(data) == 1
    for prop, value in data.items():
        control = find_control(mapping, prop, value)
        # Rule: hints only for a single property; feedback for every property without a control.
        if control is not None and not single:
            continue
        # Rule: once per device and property per run (and per value for buttons, where it decides the control).
        key = (device_id, prop, value if control is not None and control[0] == Platform.BUTTON else None)
        if key in _logged:
            continue
        _logged.add(key)
        if control is not None:
            _LOGGER.warning(
                "%s wrote %s = %s on %s: use %s instead",
                action, prop, value, device, _entity_id(hass, device_id, control),
            )
        else:
            others = "" if single else f" (together with {len(data) - 1} other properties)"
            _LOGGER.warning(
                "%s wrote %s = %s%s on %s, which has no control for it yet. If it does what you expect, please "
                "open an issue at %s saying what it does, so we can add one",
                action, prop, value, others, device, ISSUES_URL,
            )
