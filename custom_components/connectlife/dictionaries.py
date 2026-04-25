import yaml
from collections import defaultdict
from dataclasses import dataclass
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
COMMAND = "command"
DEVICE = "device"
DEVICE_CLASS = "device_class"
DISABLE = "disable"
HIDE = "hide"
ICON = "icon"
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
TARGET = "target"
READ_ONLY = "read_only"
STATE_CLASS = "state_class"
SWITCH = "switch"
COMBINE = "combine"
UNAVAILABLE = "unavailable"
ENTITY_CATEGORY = "entity_category"
UNKNOWN_VALUE = "unknown_value"
UNIT = "unit"

_LOGGER = logging.getLogger(__name__)


class _CombineSourceRequired(TypedDict):
    property: str


class CombineSource(_CombineSourceRequired, total=False):
    multiplier: float
    unknown_value: int


def _val(d: dict, key: str, default: Any = None) -> Any:
    """Return ``d[key]`` if the key is present with a non-None value, else ``default``.

    Used by parsers to treat ``key: ~`` (explicit null in a feature override) the
    same as the key being absent — except for ``state_class``, which tracks the
    distinction explicitly to suppress the auto-fallback in sensor.py.
    """
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

    def __init__(self, name: str, climate: dict | None):
        if climate is None:
            climate = {}
        self.target = _val(climate, TARGET)
        if self.target is None:
            _LOGGER.warning("Missing climate.target for for %s", name)
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

    def __init__(self, name: str, number: dict | None):
        if number is None:
            number = {}
        self.min_value = _val(number, MIN_VALUE)
        self.max_value = _val(number, MAX_VALUE)
        self.unit = _val(number, UNIT) or None
        self.multiplier = _val(number, MULTIPLIER)

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
    state_class_explicit: bool
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
        self.state_class_explicit = STATE_CLASS in sensor
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
    unavailable: int | None
    entity_category: EntityCategory | None
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
        self.hide = entry[HIDE] == bool(entry[HIDE]) if HIDE in entry else False
        self.disable = (
            entry[DISABLE] == bool(entry[DISABLE]) if DISABLE in entry else False
        )
        self.unavailable = _val(entry, UNAVAILABLE)
        entity_category = _val(entry, ENTITY_CATEGORY)
        self.entity_category = (
            EntityCategory[entity_category.upper()] if entity_category is not None else None
        )
        self.combine = _val(entry, COMBINE)

        if Platform.BINARY_SENSOR in entry:
            self.binary_sensor = BinarySensor(self.name, entry[Platform.BINARY_SENSOR])
        elif Platform.CLIMATE in entry:
            self.climate = Climate(self.name, entry[Platform.CLIMATE])
        elif Platform.HUMIDIFIER in entry:
            self.humidifier = Humidifier(self.name, entry[Platform.HUMIDIFIER])
        elif Platform.NUMBER in entry:
            self.number = Number(self.name, entry[Platform.NUMBER])
        elif Platform.SENSOR in entry:
            self.sensor = Sensor(self.name, entry[Platform.SENSOR])
        elif Platform.SELECT in entry:
            self.select = Select(self.name, entry[Platform.SELECT])
        elif Platform.SWITCH in entry:
            self.switch = Switch(self.name, entry[Platform.SWITCH])
        elif Platform.WATER_HEATER in entry:
            self.water_heater = WaterHeater(self.name, entry[Platform.WATER_HEATER])
        else:
            self.sensor = Sensor(self.name, {})


@dataclass
class Dictionary:
    """Data dictionary for a ConnectLife appliance"""

    # Todo: Refactor Climate dataclass
    climate: dict | None
    properties: dict[str, Property]


PLATFORM_KEYS = (
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.HUMIDIFIER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
)


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
    To convert a property to a different platform, declare the new platform
    key explicitly with the desired contents; to suppress an entity, use
    ``disable: true``.
    """
    if base is None:
        return dict(override)

    result = dict(base)
    base_plat = next((p for p in PLATFORM_KEYS if p in base), None)
    override_plat = next((p for p in PLATFORM_KEYS if p in override), None)

    for key, val in override.items():
        if key in PLATFORM_KEYS:
            continue
        result[key] = val

    if override_plat is None:
        return result
    override_val = override[override_plat]
    if base_plat == override_plat:
        inner_override = {} if override_val is None else override_val
        result[override_plat] = _merge_platform_block(base[base_plat], inner_override)
        return result
    if base_plat is not None:
        result.pop(base_plat, None)
    result[override_plat] = override_val
    return result


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
        raw_entries: dict[str, dict] = {}

        # TODO: Support default climate section
        _, base_data = _load_yaml(
            f"data_dictionaries/{appliance.device_type_code}.yaml"
        )
        if base_data is not None and PROPERTIES in base_data and base_data[PROPERTIES] is not None:
            for prop in base_data[PROPERTIES]:
                raw_entries[prop[PROPERTY]] = prop

        sub_found, sub_data = _load_yaml(f"data_dictionaries/{key}.yaml")
        if not sub_found:
            _LOGGER.warning(
                "No data dictionary found for %s (%s)",
                appliance.device_nickname,
                key,
            )
        if sub_data is not None:
            if Platform.CLIMATE in sub_data:
                climate = sub_data[Platform.CLIMATE]
            if PROPERTIES in sub_data and sub_data[PROPERTIES] is not None:
                for prop in sub_data[PROPERTIES]:
                    name = prop[PROPERTY]
                    raw_entries[name] = _merge_property(raw_entries.get(name), prop)

        properties: dict[str, Property] = defaultdict(
            lambda: Property({PROPERTY: "default", HIDE: True})
        )
        for name, entry in raw_entries.items():
            properties[name] = Property(entry)

        for prop in list(properties.values()):
            if prop.combine:
                for source in prop.combine:
                    properties[source[PROPERTY]].disable = True

        dictionary = Dictionary(climate=climate, properties=properties)
        cls.dictionaries[key] = dictionary
        return dictionary
