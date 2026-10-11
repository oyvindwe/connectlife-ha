import pprint
import sys
from os import listdir
from os.path import isfile, join

from jschon import create_catalog, JSON, JSONSchema
import yaml

from homeassistant.components.climate import HVACAction
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.number.const import DEVICE_CLASS_UNITS as NUMBER_DEVICE_CLASS_UNITS
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor.const import (
    DEVICE_CLASS_STATE_CLASSES,
    DEVICE_CLASS_UNITS as SENSOR_DEVICE_CLASS_UNITS,
)

from custom_components.connectlife.climate import HVAC_MODE_ALIASES, HVAC_MODE_VALUES
from custom_components.connectlife.dictionaries import _merge_property
from custom_components.connectlife.utils import normalize_temperature_unit

PLATFORMS = ('binary_sensor', 'climate', 'humidifier', 'number', 'select',
             'sensor', 'switch', 'water_heater')

HVAC_ACTION_VALUES = {action.value for action in HVACAction}


def my_construct_mapping(self, node, deep=False):
    data = self.construct_mapping_org(node, deep)
    return {(str(key) if isinstance(key, int) else key): data[key] for key in data}


def _is_sensor_platform(entry):
    """Return True if the merged property entry resolves to a sensor entity.

    A property is a sensor when it has an explicit ``sensor:`` key, or no
    platform key at all (default sensor)."""
    explicit = next((p for p in PLATFORMS if p in entry), None)
    return explicit == 'sensor' or explicit is None


def _check_entity_category_config_on_sensor(filename, merged_entry):
    """HA rejects sensors with ``entity_category: config`` — that category is
    reserved for entities the user can change directly (numbers, selects,
    switches). Catch the combination at validation time so it fails the PR
    rather than the integration setup."""
    if merged_entry.get('entity_category') != 'config':
        return None
    if not _is_sensor_platform(merged_entry):
        return None
    return (
        f"{filename}: property '{merged_entry['property']}' resolves to a "
        f"sensor with entity_category=config. HA only allows config on "
        f"writable entities (number/select/switch); use diagnostic or "
        f"omit the category for sensors."
    )


def _check_hvac_option_values(filename, merged_entry):
    """``hvac_mode`` and ``hvac_action`` options must map to values Home
    Assistant understands. An unknown ``hvac_mode`` value is silently dropped
    at runtime — the entity shows ``unknown`` for that device state with no
    warning — so catch it at validation time instead. ``hvac_action`` is logged
    but otherwise ignored at runtime; validate it for the same reason.

    A value is legal if it is a member of the corresponding HA enum, or — for
    ``hvac_mode`` — a key in ``climate.HVAC_MODE_ALIASES`` (e.g. ``eco`` →
    ``cool``). Aliased values are display-only; see climate.py."""
    climate = merged_entry.get('climate')
    if not climate:
        return None
    options = climate.get('options')
    if not options:
        return None
    target = climate.get('target')
    if target == 'hvac_mode':
        legal = HVAC_MODE_VALUES | set(HVAC_MODE_ALIASES)
    elif target == 'hvac_action':
        legal = HVAC_ACTION_VALUES
    else:
        return None
    illegal = sorted({v for v in options.values() if v not in legal})
    if not illegal:
        return None
    alias_note = " or an alias in HVAC_MODE_ALIASES" if target == 'hvac_mode' else ""
    return (
        f"{filename}: property '{merged_entry['property']}' maps {target} to "
        f"unknown value(s) {illegal}. Allowed: HA {target} states{alias_note}."
    )


PER_PROPERTY_PLATFORMS = ('binary_sensor', 'number', 'select', 'sensor', 'switch')
FALLBACK_UNSUPPORTED_DEVICE_PLATFORMS = ('humidifier', 'water_heater')


def _check_device_platform_pairing(filename, merged_entry):
    """A property may pair ``climate`` with a per-property platform — climate is
    the only device-level platform with a per-appliance target-fallback skip
    (``climate_bound_properties``), so the per-property entity is correctly
    suppressed when climate wins the target (e.g. ``t_up_down``: switch +
    ``climate`` swing_mode). ``humidifier``/``water_heater`` have no such skip,
    so pairing one with a per-property platform would create a duplicate entity.
    Reject it until those platforms grow the same fallback mechanism."""
    device = next((p for p in FALLBACK_UNSUPPORTED_DEVICE_PLATFORMS if p in merged_entry), None)
    if device is None:
        return None
    per_property = next((p for p in PER_PROPERTY_PLATFORMS if p in merged_entry), None)
    if per_property is None:
        return None
    return (
        f"{filename}: property '{merged_entry['property']}' pairs {device} with "
        f"{per_property}. Only climate supports a per-property fallback; "
        f"{device} paired with a per-property platform would create a duplicate "
        f"entity."
    )


DEVICE_CLASS_PLATFORMS = (
    ('sensor', SensorDeviceClass, SENSOR_DEVICE_CLASS_UNITS),
    ('number', NumberDeviceClass, NUMBER_DEVICE_CLASS_UNITS),
)


def _check_device_class_units(filename, merged_entry):
    """A sensor or number ``device_class`` must exist, and its ``unit`` (and a
    sensor's ``state_class``) must be one Home Assistant accepts for it. HA only
    logs a warning at runtime for a mismatch, so catch it here. The tables come
    from the installed Home Assistant, which is the minimum supported version, so
    a unit added in a later release fails until the minimum is raised.

    ``property.<name>`` units are resolved at runtime and are not checked."""
    errors = []
    for platform, device_class_enum, device_class_units in DEVICE_CLASS_PLATFORMS:
        block = merged_entry.get(platform)
        if not isinstance(block, dict) or not block.get('device_class'):
            continue
        device_class = block['device_class']
        try:
            device_class = device_class_enum(device_class)
        except ValueError:
            errors.append(f"unknown {platform} device_class '{device_class}'")
            continue
        unit = block.get('unit')
        allowed_units = device_class_units.get(device_class)
        if allowed_units is not None and not (isinstance(unit, str) and unit.startswith('property.')):
            normalized = normalize_temperature_unit(unit) if unit is not None else None
            if normalized not in allowed_units:
                allowed = sorted(str(u) for u in allowed_units if u is not None)
                errors.append(
                    f"unit '{unit}' is not valid for {platform} device_class "
                    f"'{device_class}'. Allowed: {allowed}"
                )
        state_class = block.get('state_class')
        if platform == 'sensor' and state_class and device_class in DEVICE_CLASS_STATE_CLASSES:
            allowed_state_classes = {str(s) for s in DEVICE_CLASS_STATE_CLASSES[device_class]}
            if state_class not in allowed_state_classes:
                errors.append(
                    f"state_class '{state_class}' is not valid for device_class "
                    f"'{device_class}'. Allowed: {sorted(allowed_state_classes)}"
                )
    if not errors:
        return None
    return "\n".join(
        f"{filename}: property '{merged_entry['property']}': {error}" for error in errors
    )


CHECKS = (
    _check_entity_category_config_on_sensor,
    _check_hvac_option_values,
    _check_device_platform_pairing,
    _check_device_class_units,
)


def main(basedir):
    yaml.SafeLoader.construct_mapping_org = yaml.SafeLoader.construct_mapping
    yaml.SafeLoader.construct_mapping = my_construct_mapping

    device_dir = f"{basedir}/data_dictionaries"
    create_catalog("2020-12")
    schema_file = f"{device_dir}/properties-schema.json"
    schema = JSONSchema.loadf(schema_file)
    schema.validate()

    filenames = list(filter(lambda f: f[-5:] == ".yaml", [f for f in listdir(device_dir) if isfile(join(device_dir, f))]))
    filenames.sort()

    # Pre-load base files so we can merge subtype entries before checking
    # cross-cutting rules like "no config on sensors".
    bases = {}
    for filename in filenames:
        if '-' in filename.removesuffix('.yaml'):
            continue
        type_code = filename.removesuffix('.yaml')
        with open(f"{device_dir}/{filename}") as f:
            doc = yaml.safe_load(f) or {}
        bases[type_code] = {p['property']: p for p in (doc.get('properties') or [])}

    errors = []
    for filename in filenames:
        print(f"Validating {filename}")
        with open(f"{device_dir}/{filename}", "r") as f:
            mappings_yaml = yaml.safe_load(f)
        if mappings_yaml is None:
            print("Empty mapping file")
            continue
        mappings_json = JSON(mappings_yaml)
        result = schema.evaluate(mappings_json)
        if not result.valid:
            pprint.pp(result.output("basic")["errors"])
            errors.append(filename)

        # Cross-cutting rule checks on merged property entries
        is_subtype = '-' in filename.removesuffix('.yaml')
        type_code = filename.split('-')[0] if is_subtype else filename.removesuffix('.yaml')
        base_props = bases.get(type_code, {}) if is_subtype else {}
        for prop in (mappings_yaml.get('properties') or []):
            name = prop['property']
            merged = _merge_property(base_props.get(name), prop) if is_subtype else prop
            for check in CHECKS:
                err = check(filename, merged)
                if err:
                    print(err)
                    errors.append(filename)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main("custom_components/connectlife")
