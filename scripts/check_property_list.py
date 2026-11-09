"""Check a mapping against the ConnectLife property list of its feature code.

The property list (in device diagnostics as `property_list`, or from
`python -m connectlife.dump --query property-list ...`) says which properties are read-only and which values and
ranges they take. This reports:

- OPTION: a mapped option value that isn't in the property's value list.
- READONLY: a writable platform (switch, select, number, writable climate/humidifier/water heater target) on a
  read-only property, without a separate `command` property.
- RANGE: a number/climate/water heater/humidifier min or max outside the list's limits.
- MISSING (with --all): values in the list that a mapped options dict doesn't cover.

The lists aren't perfect (typos, missing values, inconsistent formats), so check each finding against the device.

Usage, from the repository root:
    uv run python -m scripts.check_property_list <diagnostics.json>
    uv run python -m scripts.check_property_list <property-list.json> --feature <type>-<feature>
Exits with 1 if there are OPTION, READONLY or RANGE findings.
"""

import argparse
import json
import re
import sys
from types import SimpleNamespace
from typing import Any

from homeassistant.const import Platform

from custom_components.connectlife.device_mappings import DeviceMappings
from custom_components.connectlife.utils import has_platform

WRITABLE_CLIMATE = {"is_on", "target_temperature", "target_humidity", "hvac_mode", "fan_mode", "swing_mode",
                    "swing_horizontal_mode", "target_temperature_high", "target_temperature_low"}
WRITABLE_HUMIDIFIER = {"is_on", "target_humidity", "mode"}
WRITABLE_WATER_HEATER = {"is_on", "target_temperature", "current_operation", "is_away_mode_on"}
CLEAR = ("OPTION", "READONLY", "RANGE")


def parse_values(value_list: Any) -> tuple[set[int] | None, bool]:
    """Return (the integer values in a property list's value list, whether other values are allowed).

    Value lists come as "0,1", "0:close,1:auto", separated by commas, newlines or full-width punctuation, with
    "Other:..." or a Chinese note ("大于等于5…": 5 and up) for open lists, or as a plain description
    ("SelectedProgramId"). Returns None if no integer values could be read.
    """
    if not value_list or not isinstance(value_list, str):
        return None, True
    text = value_list.translate(str.maketrans({"，": ",", "；": ",", "：": ":", ";": ",", "。": ","}))
    # "0close" style entries without a colon
    text = re.sub(r"(?:^|(?<=,))\s*(-?\d+)\s*([A-Za-z])", r"\1:\2", text)
    open_list = bool(re.search(r"(?i)\bother\b|大于|≥|>=", text))
    if ":" in text:
        values = {int(m) for m in re.findall(r"(?:^|[,\n\s])\s*(-?\d+)\s*:", text)}
    else:
        parts = [p.strip() for p in re.split(r"[,\n]", text) if p.strip()]
        if not parts or not all(re.fullmatch(r"-?\d+", p) for p in parts):
            return None, True
        values = {int(p) for p in parts}
    return (values or None), open_list


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _limits(value: Any) -> list[float]:
    """A mapping min/max is a number or a per-unit dict ({"°C": 16, "°F": 61}); the lists use °C."""
    if isinstance(value, dict):
        celsius = value.get("°C")
        return [celsius] if isinstance(celsius, (int, float)) else []
    return [value] if isinstance(value, (int, float)) else []


def check(type_code: str, feature: str, property_list: dict) -> list[tuple[str, str, str]]:
    """Return findings as (kind, property, detail) for the mapping of a feature code."""
    appliance: Any = SimpleNamespace(
        device_type_code=type_code, device_feature_code=feature,
        device_feature_name="", device_type_name="", device_nickname=f"{type_code}-{feature}",
    )
    mapping = DeviceMappings.get_mapping(appliance)
    findings = []
    for entry in property_list.get("properties") or []:
        name = entry.get("propertyKey")
        if name not in mapping.properties:  # dict.get on the defaultdict doesn't create entries
            continue
        prop = mapping.properties[name]
        if prop.disable:
            continue
        read_write = (entry.get("propertyRW") or "").strip()
        values, open_list = parse_values(entry.get("propertyValueList"))

        writable = []
        for platform in (Platform.SWITCH, Platform.SELECT, Platform.NUMBER):
            if has_platform(platform, prop) and not getattr(getattr(prop, platform.value), "command_name", None):
                writable.append(platform.value)
        if has_platform(Platform.CLIMATE, prop) and prop.climate.target in WRITABLE_CLIMATE:
            writable.append(f"climate {prop.climate.target}")
        if has_platform(Platform.HUMIDIFIER, prop) and prop.humidifier.target in WRITABLE_HUMIDIFIER:
            writable.append(f"humidifier {prop.humidifier.target}")
        if has_platform(Platform.WATER_HEATER, prop) and prop.water_heater.target in WRITABLE_WATER_HEATER:
            writable.append(f"water_heater {prop.water_heater.target}")
        if writable and read_write == "R":
            findings.append(("READONLY", name, f"{', '.join(writable)} on a read-only property"))

        options = {}
        for platform in ("sensor", "select", "climate", "humidifier", "water_heater"):
            obj = getattr(prop, platform, None)
            if obj is not None and getattr(obj, "options", None):
                options = obj.options
                break
        binary = getattr(prop, "binary_sensor", None)
        if not options and binary is not None and "options" in vars(binary):
            options = binary.options
        if options and values is not None:
            keys = {k for k in options if isinstance(k, int)}
            extra = sorted(keys - values)
            if extra and not open_list:
                findings.append(("OPTION", name, f"mapped {extra} not in the list "
                                 f"({entry.get('propertyValueList')!r})"))
            missing = sorted(values - keys)
            if missing:
                findings.append(("MISSING", name, f"list has {missing} not mapped "
                                 f"({entry.get('propertyValueList')!r})"))

        low, high = _to_float(entry.get("lowerLimit")), _to_float(entry.get("upperLimit"))
        if low is not None or high is not None:
            for platform in ("number", "climate", "water_heater", "humidifier"):
                obj = getattr(prop, platform, None)
                if obj is None or not has_platform(Platform(platform), prop):
                    continue
                multiplier = getattr(obj, "multiplier", None) or 1
                for kind, value in (("min", getattr(obj, "min_value", None)), ("max", getattr(obj, "max_value", None))):
                    for limit in _limits(value):
                        raw = limit / multiplier
                        if (low is not None and raw < low) or (high is not None and raw > high):
                            findings.append(("RANGE", name, f"{platform} {kind} {limit} outside the list's "
                                             f"{entry.get('lowerLimit')}..{entry.get('upperLimit')}"))
    return findings


def load(path: str, feature: str | None) -> tuple[str, str, dict]:
    """Return (type code, feature code, property list) from a diagnostics or property list file."""
    with open(path) as f:
        data = json.load(f, strict=False)
    appliance = data.get("data") if isinstance(data.get("data"), dict) else data.get("appliance")
    if isinstance(appliance, dict) and "property_list" in appliance:  # diagnostics
        type_code, feature_code = appliance["device_type_code"], appliance["device_feature_code"]
        property_list = appliance["property_list"] or {}
    else:  # connectlife.dump --query property-list
        property_list = data
        type_code = data.get("deviceTypeCode")
        feature_code = data.get("deviceFeactureCode") or data.get("deviceFeatureCode")  # sic
    if feature:
        type_code, feature_code = feature.split("-", 1)
    if not type_code or not feature_code:
        sys.exit("Can't tell the device type and feature code; pass --feature <type>-<feature>")
    return type_code, feature_code, property_list


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="Device diagnostics, or a property list from connectlife.dump")
    parser.add_argument("--feature", help="<type>-<feature> of the mapping to check, e.g. 025-1wj090908v0w")
    parser.add_argument("--all", action="store_true", help="Also show list values that aren't mapped")
    args = parser.parse_args()

    type_code, feature_code, property_list = load(args.file, args.feature)
    if not property_list.get("properties"):
        print(f"{type_code}-{feature_code}: the property list is empty, nothing to check")
        return
    findings = [f for f in check(type_code, feature_code, property_list) if args.all or f[0] in CLEAR]
    print(f"{type_code}-{feature_code}: {len(property_list['properties'])} properties in the list")
    for kind, name, detail in sorted(findings):
        print(f"  {kind} {name}: {detail}")
    if any(kind in CLEAR for kind, _, _ in findings):
        sys.exit(1)
    if not findings:
        print("  no findings")


if __name__ == "__main__":
    main()
