import yaml
from collections import defaultdict
from dataclasses import dataclass, field
import logging
import pkgutil
from typing import Any, TypedDict

from connectlife.appliance import ConnectLifeAppliance
from homeassistant.const import Platform, EntityCategory
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.humidifier import HumidifierDeviceClass
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.components.water_heater import STATE_OFF

from .const import (
    ACTION,
    CURRENT_OPERATION,
    FAN_MODE,
    HVAC_ACTION,
    HVAC_MODE,
    IS_AWAY_MODE_ON,
    MODE,
    STATE,
    SWING_MODE,
    TEMPERATURE_UNIT,
)

ADJUST = "adjust"
AVAILABLE_WHEN = "available_when"
BUTTONS = "buttons"
COMMAND = "command"
DEVICE = "device"
DEVICE_CLASS = "device_class"
STATISTICS = "statistics"
SOURCE = "source"
DISABLE = "disable"
HIDE = "hide"
ICON = "icon"
KEY = "key"
NAME = "name"
OFF = "off"
ON = "on"
OPTIONS = "options"
PRESETS = "presets"
PROPERTY = "property"
PROPERTIES = "properties"
MAX_VALUE = "max_value"
MIN_VALUE = "min_value"
MULTIPLIER = "multiplier"
OPTIONAL = "optional"
PRIORITY = "priority"
TARGET = "target"
READ_ONLY = "read_only"
STATE_CLASS = "state_class"
SWITCH = "switch"
COMBINE = "combine"
UNAVAILABLE = "unavailable"
ENTITY_CATEGORY = "entity_category"
TRANSLATION_KEY = "translation_key"
UNKNOWN_VALUE = "unknown_value"
UNIT = "unit"
WRITE = "write"

_LOGGER = logging.getLogger(__name__)


class _CombineSourceRequired(TypedDict):
    property: str


class CombineSource(_CombineSourceRequired, total=False):
    multiplier: float
    unknown_value: int


def _val(d: dict, key: str, default: Any = None) -> Any:
    """Return ``d[key]`` if the key is present with a non-None value, else ``default``."""
    if key in d and d[key] is not None:
        return d[key]
    return default


class BinarySensor:
    device_class: BinarySensorDeviceClass | None
    options: dict[int, bool] = {0: False, 1: False, 2: True}

    def __init__(self, name: str, binary_sensor: dict | None):
        if binary_sensor is None:
            binary_sensor = {}
        device_class = _val(binary_sensor, DEVICE_CLASS)
        self.device_class = (
            BinarySensorDeviceClass(device_class) if device_class is not None else None
        )
        options = _val(binary_sensor, OPTIONS)
        if options is not None:
            self.options = options


class Climate:
    target: str | None
    options: dict
    unknown_value: int | None
    min_value: int | dict[str, int] | None
    max_value: int | dict[str, int] | None
    # Tie-break when several properties map to the same climate target. The
    # lowest-priority candidate that the device actually exposes wins the
    # target; the rest fall back to their per-property platform (if any). Lower
    # number = preferred. Default is intentionally large so explicitly-ranked
    # candidates win.
    priority: int

    def __init__(self, name: str, climate: dict | None):
        if climate is None:
            climate = {}
        self.target = _val(climate, TARGET)
        if self.target is None:
            _LOGGER.warning("Missing climate.target for for %s", name)
        self.priority = _val(climate, PRIORITY, 100)
        self.options = _val(climate, OPTIONS, {})
        if not self.options and self.target in [
            FAN_MODE,
            HVAC_ACTION,
            HVAC_MODE,
            SWING_MODE,
            TEMPERATURE_UNIT,
        ]:
            _LOGGER.warning("Missing climate.options for %s", name)
        self.unknown_value = _val(climate, UNKNOWN_VALUE)
        self.min_value = _val(climate, MIN_VALUE)
        self.max_value = _val(climate, MAX_VALUE)


class Humidifier:
    target: str | None
    options: dict
    device_class: HumidifierDeviceClass | None
    min_value: int | None
    max_value: int | None

    def __init__(self, name: str, humidifier: dict | None):
        if humidifier is None:
            humidifier = {}
        self.target = _val(humidifier, TARGET)
        if self.target is None:
            _LOGGER.warning("Missing humidifier.target for for %s", name)
        self.options = _val(humidifier, OPTIONS, {})
        if not self.options and self.target in [ACTION, MODE]:
            _LOGGER.warning("Missing humidifier.options for %s", name)
        device_class = _val(humidifier, DEVICE_CLASS)
        self.device_class = (
            HumidifierDeviceClass(device_class) if device_class is not None else None
        )
        self.min_value = _val(humidifier, MIN_VALUE)
        self.max_value = _val(humidifier, MAX_VALUE)


class Number:
    min_value: int | None
    max_value: int | None
    multiplier: float | None
    device_class: NumberDeviceClass | None
    unit: str | None
    command_name: str | None

    def __init__(self, name: str, number: dict | None):
        if number is None:
            number = {}
        self.min_value = _val(number, MIN_VALUE)
        self.max_value = _val(number, MAX_VALUE)
        self.unit = _val(number, UNIT) or None
        self.multiplier = _val(number, MULTIPLIER)
        command = _val(number, COMMAND, {})
        self.command_name = _val(command, NAME)

        device_class = None
        device_class_value = _val(number, DEVICE_CLASS)
        if device_class_value is not None:
            device_class = NumberDeviceClass(device_class_value)
            if (
                device_class == NumberDeviceClass.PH
                or device_class == NumberDeviceClass.AQI
            ):
                if self.unit:
                    _LOGGER.warning(
                        "%s has device class %s and unit %s",
                        name,
                        device_class,
                        self.unit,
                    )
                    self.unit = None
            elif not self.unit:
                _LOGGER.warning("%s has device class, but no unit", name)
                device_class = None
        self.device_class = device_class


class Select:
    options: dict
    unknown_value: int | None
    command_name: str | None
    command_adjust: int = 0

    def __init__(self, name: str, select: dict | None):
        if select is None:
            select = {}
        options = _val(select, OPTIONS)
        if options is None:
            _LOGGER.warning("Select %s has no options", name)
            self.options = {}
        else:
            self.options = options
        self.unknown_value = _val(select, UNKNOWN_VALUE)
        command = _val(select, COMMAND, {})
        self.command_name = _val(command, NAME)
        self.command_adjust = _val(command, ADJUST, 0)


class Sensor:
    unknown_value: int | None
    min_value: int | None
    max_value: int | None
    multiplier: float | None
    read_only: bool | None
    state_class: SensorStateClass | None
    device_class: SensorDeviceClass | None
    unit: str | None
    options: dict[int, str] | None

    def __init__(self, name: str, sensor: dict | None):
        if sensor is None:
            sensor = {}
        self.unknown_value = _val(sensor, UNKNOWN_VALUE)
        self.read_only = _val(sensor, READ_ONLY)
        self.unit = _val(sensor, UNIT) or None
        self.multiplier = _val(sensor, MULTIPLIER)
        state_class_value = _val(sensor, STATE_CLASS)
        self.state_class = (
            SensorStateClass(state_class_value) if state_class_value is not None else None
        )

        device_class = None
        device_class_value = _val(sensor, DEVICE_CLASS)
        if device_class_value is not None:
            device_class = SensorDeviceClass(device_class_value)
            if device_class == SensorDeviceClass.ENUM:
                if self.unit:
                    _LOGGER.warning("%s has device class enum, but has unit", name)
                    device_class = None
                if self.state_class:
                    _LOGGER.warning(
                        "%s has device class enum, but has state_class", name
                    )
                    device_class = None
                options = _val(sensor, OPTIONS)
                if device_class and options is None:
                    _LOGGER.warning("%s has device class enum, but no options", name)
                    device_class = None
                else:
                    self.options = options
            elif device_class in [
                SensorDeviceClass.AQI,
                SensorDeviceClass.DATE,
                SensorDeviceClass.PH,
                SensorDeviceClass.TIMESTAMP,
            ]:
                if self.unit:
                    _LOGGER.warning(
                        "%s has device class %s and unit %s",
                        name,
                        device_class,
                        self.unit,
                    )
                    self.unit = None
            elif not self.unit:
                _LOGGER.warning("%s has device class, but no unit", name)
                device_class = None
        self.device_class = device_class


class Switch:
    device_class: SwitchDeviceClass | None
    off: int
    on: int
    command_name: str | None
    command_adjust: int = 0

    def __init__(self, name: str, switch: dict | None):
        if switch is None:
            switch = {}
        device_class = _val(switch, DEVICE_CLASS)
        self.device_class = (
            SwitchDeviceClass(device_class) if device_class is not None else None
        )
        self.off = _val(switch, OFF, 0)
        self.on = _val(switch, ON, 1)
        command = _val(switch, COMMAND, {})
        self.command_name = _val(command, NAME)
        self.command_adjust = _val(command, ADJUST, 0)


class WaterHeater:
    target: str | None
    options: dict
    unknown_value: int | None
    min_value: int | dict[str, int] | None
    max_value: int | dict[str, int] | None

    def __init__(self, name: str, water_heater: dict | None):
        if water_heater is None:
            water_heater = {}
        self.target = _val(water_heater, TARGET)
        if self.target is None:
            _LOGGER.warning("Missing water_heater.target for for %s", name)
        self.options = _val(water_heater, OPTIONS, {})
        if not self.options and self.target in [
            CURRENT_OPERATION,
            IS_AWAY_MODE_ON,
            STATE,
            TEMPERATURE_UNIT,
        ]:
            _LOGGER.warning("Missing water_heater.options for %s", name)
        if self.target == STATE and STATE_OFF not in self.options.values():
            _LOGGER.warning("Missing state off for water_heater.options for %s", name)
        if self.target == STATE and len(self.options) < 2:
            _LOGGER.warning(
                "Require at least 2 valid states in water_heater.options for %s", name
            )
        self.unknown_value = _val(water_heater, UNKNOWN_VALUE)
        self.min_value = _val(water_heater, MIN_VALUE)
        self.max_value = _val(water_heater, MAX_VALUE)


class Property:
    name: str
    icon: str | None
    hide: bool
    disable: bool
    optional: bool
    unavailable: int | None
    entity_category: EntityCategory | None
    translation_key: str | None
    combine: list[CombineSource] | None
    binary_sensor: BinarySensor
    climate: Climate
    humidifier: Humidifier
    number: Number
    sensor: Sensor
    select: Select
    switch: Switch
    water_heater: WaterHeater

    def __init__(self, entry: dict):
        self.name = entry[PROPERTY]
        self.icon = _val(entry, ICON) or None
        self.hide = bool(entry[HIDE]) if HIDE in entry else False
        self.disable = bool(entry[DISABLE]) if DISABLE in entry else False
        self.optional = bool(entry[OPTIONAL]) if OPTIONAL in entry else False
        self.unavailable = _val(entry, UNAVAILABLE)
        entity_category = _val(entry, ENTITY_CATEGORY)
        self.entity_category = (
            EntityCategory[entity_category.upper()] if entity_category is not None else None
        )
        self.combine = _val(entry, COMBINE)
        self.translation_key = _val(entry, TRANSLATION_KEY)

        # A property may carry one device-level platform (climate / humidifier /
        # water_heater) AND one per-property platform (binary_sensor / number /
        # select / sensor / switch). The device-level block acts as a target
        # candidacy; when the device also exposes a higher-priority candidate for
        # that target, this property falls back to its per-property platform.
        if Platform.CLIMATE in entry:
            self.climate = Climate(self.name, entry[Platform.CLIMATE])
        elif Platform.HUMIDIFIER in entry:
            self.humidifier = Humidifier(self.name, entry[Platform.HUMIDIFIER])
        elif Platform.WATER_HEATER in entry:
            self.water_heater = WaterHeater(self.name, entry[Platform.WATER_HEATER])

        if Platform.BINARY_SENSOR in entry:
            self.binary_sensor = BinarySensor(self.name, entry[Platform.BINARY_SENSOR])
        elif Platform.NUMBER in entry:
            self.number = Number(self.name, entry[Platform.NUMBER])
        elif Platform.SENSOR in entry:
            self.sensor = Sensor(self.name, entry[Platform.SENSOR])
        elif Platform.SELECT in entry:
            self.select = Select(self.name, entry[Platform.SELECT])
        elif Platform.SWITCH in entry:
            self.switch = Switch(self.name, entry[Platform.SWITCH])
        elif not any(p in entry for p in PLATFORM_KEYS):
            self.sensor = Sensor(self.name, {})


class Button:
    """A button entity declared at the top level of a data dictionary.

    Buttons are for write-only commands: a press writes ``write`` to the
    device. ``available_when`` gates the button on read-back property values
    (all keys must match for the button to be available).
    """

    key: str
    icon: str | None
    available_when: dict[str, int]
    write: dict[str, int]

    def __init__(self, entry: dict):
        self.key = entry[KEY]
        self.icon = _val(entry, ICON) or None
        self.available_when = _val(entry, AVAILABLE_WHEN, {})
        write = _val(entry, WRITE)
        if not write:
            _LOGGER.warning("Button %s has no write map", self.key)
            self.write = {}
        else:
            self.write = write


def _merge_buttons(base: list[dict], override: list[dict]) -> list[dict]:
    """Merge button lists by ``key``.

    Entries in ``override`` matching a key in ``base`` shallow-merge field by
    field (override wins; ``available_when`` and ``write`` replace as a whole
    since they're collections). Entries with keys not in ``base`` are
    appended. ``disable: true`` removes the merged entry from the result —
    use it to suppress an inherited button on a variant that doesn't support
    the action.
    """
    by_key: dict[str, dict] = {b[KEY]: dict(b) for b in base}
    order: list[str] = [b[KEY] for b in base]
    for entry in override:
        key = entry[KEY]
        if key in by_key:
            by_key[key] = {**by_key[key], **entry}
        else:
            by_key[key] = dict(entry)
            order.append(key)
    return [by_key[k] for k in order if not by_key[k].get(DISABLE)]


@dataclass
class Dictionary:
    """Data dictionary for a ConnectLife appliance"""

    # Todo: Refactor Climate dataclass
    climate: dict | None
    properties: dict[str, Property]
    buttons: list[Button]
    # Cloud statistics endpoint for this device family (None = none): "air_duct_energy"
    # (air conditioners) or "energy_consumption_curve" (appliances). Dispatched via the
    # statistics_sources registry.
    statistics_source: str | None = None
    # Per-sensor flags from the `statistics` block (sensor key -> create?). A sensor is
    # created only when listed true here; omitted or false means not created.
    statistics_sensors: dict[str, bool] = field(default_factory=dict)


# Device-level platforms own a `target` and may coexist with a per-property
# platform on the same property (the per-property block is the fallback when
# another property wins the target).
DEVICE_PLATFORM_KEYS = (
    Platform.CLIMATE,
    Platform.HUMIDIFIER,
    Platform.WATER_HEATER,
)
PER_PROPERTY_PLATFORM_KEYS = (
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
)
PLATFORM_KEYS = DEVICE_PLATFORM_KEYS + PER_PROPERTY_PLATFORM_KEYS


def _merge_property(base: dict | None, override: dict) -> dict:
    """Merge ``override`` on top of ``base``.

    Top-level fields and platform-block fields inherit field-by-field from the
    base when the platform is unchanged. Collections (``options``, ``combine``,
    dict-valued ``min_value``/``max_value``, ``command``) replace as a whole.
    A field set to ``None`` in the override is preserved as ``None`` so parsers
    can detect "explicitly unset" — meaningful for ``state_class``, equivalent
    to absent for everything else.

    A bare platform key in the override (``switch:`` with no value, parsed as
    ``None``) is YAML shorthand for ``{}``: it means "this property uses the
    given platform with no overrides", not "remove the platform from base".

    A property's platforms are merged in two independent groups — the
    device-level platform (climate / humidifier / water_heater) and the
    per-property platform (binary_sensor / number / select / sensor / switch).
    Within a group, declaring a different platform key replaces the base's; an
    override that touches only one group leaves the other intact (so a subtype
    adding a ``climate`` candidacy keeps the base ``switch`` as the fallback,
    and a subtype tweaking the ``switch`` keeps the inherited ``climate``).
    To suppress an entity, use ``disable: true``.
    """
    if base is None:
        return dict(override)

    result = dict(base)
    for key, val in override.items():
        if key in PLATFORM_KEYS:
            continue
        result[key] = val

    for group in (PER_PROPERTY_PLATFORM_KEYS, DEVICE_PLATFORM_KEYS):
        _merge_platform_group(result, base, override, group)
    return result


def _merge_platform_group(result: dict, base: dict, override: dict, group: tuple) -> None:
    """Merge the ``override`` platform within ``group`` onto ``result`` in place.

    ``result`` already carries the base's platform for this group (it starts as
    a copy of ``base``). If the override declares no platform in this group, the
    base's platform is left untouched.
    """
    base_plat = next((p for p in group if p in base), None)
    override_plat = next((p for p in group if p in override), None)
    if override_plat is None:
        return
    override_val = override[override_plat]
    if base_plat == override_plat:
        inner_override = {} if override_val is None else override_val
        result[override_plat] = _merge_platform_block(base[base_plat], inner_override)
        return
    if base_plat is not None:
        result.pop(base_plat, None)
    result[override_plat] = override_val


def _merge_platform_block(base, override):
    if override is None:
        return None
    if base is None:
        return dict(override)
    result = dict(base)
    result.update(override)
    return result


def _load_yaml(path: str) -> tuple[bool, Any]:
    """Return ``(found, parsed_yaml)``.

    An empty file (a subtype file with only ``# Uses default mappings``) is
    ``(True, None)`` — present, no overrides — distinct from a missing file
    ``(False, None)``, so callers don't emit spurious "no data dictionary
    found" warnings for placeholder subtype files.
    """
    try:
        data = pkgutil.get_data(__name__, path)
    except FileNotFoundError:
        return False, None
    if data is None:
        return False, None
    return True, yaml.safe_load(data)


class Dictionaries:

    dictionaries: dict[str, Dictionary] = {}

    @classmethod
    def get_dictionary(cls, appliance: ConnectLifeAppliance) -> Dictionary:
        key = f"{appliance.device_type_code}-{appliance.device_feature_code}"
        if key in cls.dictionaries:
            return cls.dictionaries[key]

        climate: dict | None = None
        statistics: dict | None = None
        raw_entries: dict[str, dict] = {}
        raw_buttons: list[dict] = []

        # TODO: Support default climate section
        _, base_data = _load_yaml(
            f"data_dictionaries/{appliance.device_type_code}.yaml"
        )
        if base_data is not None:
            statistics = _val(base_data, STATISTICS, statistics)
            if PROPERTIES in base_data and base_data[PROPERTIES] is not None:
                for prop in base_data[PROPERTIES]:
                    raw_entries[prop[PROPERTY]] = prop
            if BUTTONS in base_data and base_data[BUTTONS] is not None:
                raw_buttons = list(base_data[BUTTONS])

        sub_found, sub_data = _load_yaml(f"data_dictionaries/{key}.yaml")
        if not sub_found:
            _LOGGER.warning(
                "No data dictionary found for %s (%s)",
                appliance.device_nickname,
                key,
            )
        if sub_data is not None:
            statistics = _val(sub_data, STATISTICS, statistics)
            if Platform.CLIMATE in sub_data:
                climate = sub_data[Platform.CLIMATE]
            if PROPERTIES in sub_data and sub_data[PROPERTIES] is not None:
                for prop in sub_data[PROPERTIES]:
                    name = prop[PROPERTY]
                    raw_entries[name] = _merge_property(raw_entries.get(name), prop)
            if BUTTONS in sub_data and sub_data[BUTTONS] is not None:
                raw_buttons = _merge_buttons(raw_buttons, sub_data[BUTTONS])

        properties: dict[str, Property] = defaultdict(
            lambda: Property({PROPERTY: "default", OPTIONAL: True})
        )
        for name, entry in raw_entries.items():
            properties[name] = Property(entry)

        for prop in list(properties.values()):
            if prop.combine:
                for source in prop.combine:
                    properties[source[PROPERTY]].disable = True

        buttons = [Button(b) for b in raw_buttons]

        statistics = statistics or {}
        statistics_source = _val(statistics, SOURCE)
        statistics_sensors = {
            sensor_key: bool(create)
            for sensor_key, create in statistics.items()
            if sensor_key != SOURCE
        }

        dictionary = Dictionary(
            climate=climate,
            properties=properties,
            buttons=buttons,
            statistics_source=statistics_source,
            statistics_sensors=statistics_sensors,
        )
        cls.dictionaries[key] = dictionary
        return dictionary
