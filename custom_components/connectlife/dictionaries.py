import yaml
from collections import defaultdict
import logging
import pkgutil

from connectlife.appliance import ConnectLifeAppliance
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass


_LOGGER = logging.getLogger(__name__)

class Property:
    def __init__(self, entry: dict):
        self.status = entry["property"]
        self.unknown_value = entry["unknown_value"] if "unknown_value" in entry and entry["unknown_value"] else None
        self.max_value = entry["max_value"] if "max_value" in entry and entry["max_value"] else None
        self.hide = entry["hide"] == True if "hide" in entry else False
        self.writable = entry["writable"] if "writable" in entry else None
        if "state_class" in entry and entry["state_class"]:
            self.state_class = SensorStateClass(entry["state_class"])
        else:
            self.state_class = None
        self.unit = entry["unit"] if "unit" in entry and entry["unit"] else None
        if "device_class" in entry and entry["device_class"]:
            self.device_class = SensorDeviceClass(entry["device_class"])
            if not self.unit:
                _LOGGER.warning("%s has device class, but no unit", self.status)
        else:
            self.device_class = None


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
