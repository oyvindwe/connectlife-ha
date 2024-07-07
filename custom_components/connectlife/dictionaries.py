import yaml
from collections import defaultdict
import logging
import pkgutil

from connectlife.appliance import ConnectLifeAppliance
from homeassistant.const import Platform
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass

from .const import (
    FAN_MODE,
    HVAC_ACTION,
    SWING_MODE,
    TEMPERATURE_UNIT,
)

DEVICE_CLASS = "device_class"
HIDE = "hide"
ICON = "icon"
OFF = "off"
ON = "on"
OPTIONS = "options"
PROPERTY = "property"
PROPERTIES = "properties"
MAX_VALUE = "max_value"
TARGET = "target"
STATE_CLASS = "state_class"
SWITCH = "switch"
UNKNOWN_VALUE = "unknown_value"
UNIT = "unit"
WRITABLE = "writable"

_LOGGER = logging.getLogger(__name__)


class BinarySensor():
    device_class: BinarySensorDeviceClass | None

    def __init__(self, name: str, binary_sensor: dict | None):
        if binary_sensor is None:
            binary_sensor = {}
        self.device_class = BinarySensorDeviceClass(binary_sensor[DEVICE_CLASS]) \
            if DEVICE_CLASS in binary_sensor else None


class Climate():
    target: str
    options: dict | None

    def __init__(self, name: str, climate: dict | None):
        if climate is None:
            climate = {}
        self.target = climate[TARGET] if TARGET in climate else None
        if self.target is None:
            _LOGGER.warning("Missing climate.target for for %s", name)
        self.options = climate[OPTIONS] if OPTIONS in climate else None
        if self.options is None and self.target in [FAN_MODE, HVAC_ACTION, SWING_MODE, TEMPERATURE_UNIT]:
            _LOGGER.warning("Missing climate.options for %s", name)


class Select():
    options: dict

    def __init__(self, name: str, select: dict):
        if select is None:
            select = {}
        if not OPTIONS in select:
            _LOGGER.warning("Select %s has no options", name)
            self.options = []
        else:
            self.options = select[OPTIONS]


class Sensor():
    unknown_value: int | None
    max_value: int | None
    writeable: bool | None
    state_class: SensorStateClass | None
    device_class: SensorDeviceClass | None
    unit: str | None
    options: list[dict[int, str]] | None

    def __init__(self, name: str, sensor: dict):
        if sensor is None:
            sensor = {}
        self.unknown_value = sensor[UNKNOWN_VALUE] if UNKNOWN_VALUE in sensor and sensor[UNKNOWN_VALUE] else None
        self.writable = sensor[WRITABLE] if WRITABLE in sensor else None
        self.max_value = sensor[MAX_VALUE] if MAX_VALUE in sensor and sensor[MAX_VALUE] else None
        self.unit = sensor[UNIT] if UNIT in sensor and sensor[UNIT] else None
        self.state_class = SensorStateClass(sensor[STATE_CLASS]) if STATE_CLASS in sensor else None

        device_class = None
        if DEVICE_CLASS in sensor:
            device_class = SensorDeviceClass(sensor[DEVICE_CLASS])
            if device_class == SensorDeviceClass.ENUM:
                if self.unit:
                    _LOGGER.warning("%s has device class enum, but has unit", name)
                    device_class = None
                if self.state_class:
                    _LOGGER.warning("%s has device class enum, but has state_class", name)
                    device_class = None
                if device_class and not "options" in sensor:
                    _LOGGER.warning("%s has device class enum, but no options", name)
                    device_class = None
                else:
                    self.options = sensor["options"]
            elif device_class == SensorDeviceClass.PH:
                if self.unit:
                    _LOGGER.warning("%s has device class ph and unit %s", name, self.unit)
                    self.unit = None
            elif not self.unit:
                _LOGGER.warning("%s has device class, but no unit", name)
                device_class = None
        self.device_class = device_class


class Switch():
    device_class: SwitchDeviceClass | None
    off: int
    on: int

    def __init__(self, name: str, switch: dict):
        if switch is None:
            switch = {}
        self.device_class = SwitchDeviceClass(switch[DEVICE_CLASS])\
            if DEVICE_CLASS in switch else None
        self.off = switch[OFF] if OFF in switch else 0
        self.on = switch[ON] if ON in switch else 1


class Property:
    name: str
    icon: str | None
    hide: bool
    binary_sensor: BinarySensor | None
    climate: Climate | None
    sensor: Sensor | None
    select: Select | None
    switch: Switch | None

    def __init__(self, entry: dict):
        self.name = entry[PROPERTY]
        self.icon = entry[ICON] if ICON in entry and entry[ICON] else None
        self.hide = entry[HIDE] == bool(entry[HIDE]) if HIDE in entry else False

        if Platform.BINARY_SENSOR in entry:
            self.binary_sensor = BinarySensor(self.name, entry[Platform.BINARY_SENSOR])
        elif Platform.CLIMATE in entry:
            self.climate = Climate(self.name, entry[Platform.CLIMATE])
        elif Platform.SENSOR in entry:
            self.sensor = Sensor(self.name, entry[Platform.SENSOR])
        elif Platform.SELECT in entry:
            self.select = Select(self.name, entry[Platform.SELECT])
        elif Platform.SWITCH in entry:
            self.switch = Switch(self.name, entry[Platform.SWITCH])
        else:
            self.sensor = Sensor(self.name, {})


class Dictionaries:
    """Data dictionary for a ConnectLife appliance"""

    dictionaries: dict[str, dict[str, Property]] = {}

    @classmethod
    def get_dictionary(cls, appliance: ConnectLifeAppliance) -> dict[str, Property]:
        key = f"{appliance.device_type_code}-{appliance.device_feature_code}"
        if key in Dictionaries.dictionaries:
            return Dictionaries.dictionaries[key]
        dictionary = defaultdict(lambda: Property({PROPERTY: "default", HIDE: True}))
        try:
            data = pkgutil.get_data(__name__, f"data_dictionaries/{key}.yaml")
            parsed = yaml.safe_load(data)
            for property in parsed[PROPERTIES]:
                dictionary[property[PROPERTY]] = Property(property)
        except FileNotFoundError:
            _LOGGER.warning("No data dictionary found for %s", key)
        Dictionaries.dictionaries[key] = dictionary
        return dictionary
