import yaml
from collections import defaultdict
import logging
import pkgutil

from connectlife.appliance import ConnectLifeAppliance
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

_LOGGER = logging.getLogger(__name__)


class Sensor():
    unknown_value: int | None
    max_value: int | None
    writeable: bool | None
    state_class: SensorStateClass | None
    device_class: SensorDeviceClass | None
    unit: str | None
    options: list[dict[int, str]] | None

    def __init__(self, name: str, sensor: dict = {}):
        self.unknown_value = sensor["unknown_value"] if "unknown_value" in sensor and sensor["unknown_value"] else None
        self.writable = sensor["writable"] if "writable" in sensor else None
        self.max_value = sensor["max_value"] if "max_value" in sensor and sensor["max_value"] else None
        self.unit = sensor["unit"] if "unit" in sensor and sensor["unit"] else None
        self.state_class = SensorStateClass(sensor["state_class"]) if "state_class" in sensor else None

        device_class = None
        if "device_class" in sensor:
            device_class = SensorDeviceClass(sensor["device_class"])
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


class BinarySensor():
    device_class: BinarySensorDeviceClass | None

    def __init__(self, name: str, binary_sensor: dict):
        self.device_class = BinarySensorDeviceClass(binary_sensor["device_class"])\
            if "device_class" in binary_sensor else None


class Property:
    name: str
    icon: str | None
    hide: bool
    binary_sensor: BinarySensor | None
    sensor: Sensor | None

    def __init__(self, entry: dict):
        self.name = entry["property"]
        self.icon = entry["icon"] if "icon" in entry and entry["icon"] else None
        self.hide = entry["hide"] == True if "hide" in entry else False

        if "binary_sensor" in entry:
            self.binary_sensor = BinarySensor(self.name, entry["binary_sensor"])
        elif "sensor" in entry:
            self.sensor = Sensor(self.name, entry["sensor"])
        else:
            self.sensor = Sensor(self.name)


class Dictionaries:
    """Data dictionary for a ConnectLife appliance"""

    dictionaries: dict[str, dict[str, Property]] = {}

    @classmethod
    def get_dictionary(cls, appliance: ConnectLifeAppliance) -> dict[str, Property]:
        key = f"{appliance.device_type_code}-{appliance.device_feature_code}"
        if key in Dictionaries.dictionaries:
            return Dictionaries.dictionaries[key]
        dictionary = defaultdict(lambda: Property({"property": "default"}))
        try:
            data = pkgutil.get_data(__name__, f"data_dictionaries/{key}.yaml")
            parsed = yaml.safe_load(data)
            for property in parsed["properties"]:
                dictionary[property["property"]] = Property(property)
        except FileNotFoundError:
            _LOGGER.warning("No data dictionary found for %s", key)
        Dictionaries.dictionaries[key] = dictionary
        return dictionary
