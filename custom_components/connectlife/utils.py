import datetime as dt

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform, UnitOfTemperature

from connectlife.appliance import ConnectLifeAppliance
from .const import TEMPERATURE_UNIT
from .dictionaries import Property, Dictionary


def is_entity(platform: Platform, property: Property, value: float | int | str | dt.datetime | None):
    return (
            hasattr(property, platform)
            and not property.disable
            and (
                    property.unavailable is None
                    or value != property.unavailable
            )
    )


def to_unit(unit: str | None, appliance: ConnectLifeAppliance, dictionary: Dictionary):
    if unit is None:
        return None
    if unit.startswith("property."):
        unit_property_name = unit[9:]
        if unit_property_name in dictionary.properties:
            unit_value = appliance.status_list[unit_property_name]
            unit_property = dictionary.properties[unit_property_name]
            if is_entity(Platform.CLIMATE, unit_property, unit_value):
                unit_climate = unit_property.climate
                if unit_climate.target == TEMPERATURE_UNIT and unit_value in unit_climate.options:
                    unit = unit_climate.options[unit_value]
            elif is_entity(Platform.SENSOR, unit_property, unit_value):
                unit_sensor = unit_property.sensor
                if unit_sensor.device_class == SensorDeviceClass.ENUM and unit_sensor.options is not None and unit_value in unit_sensor.options:
                    unit = unit_sensor.options[unit_value]  # type: ignore[index]
            elif is_entity(Platform.SELECT, unit_property, unit_value):
                unit_select = unit_property.select
                if unit_value in unit_select.options:
                    unit = unit_select.options[unit_value]
    if unit is None:
        return None
    return normalize_temperature_unit(unit)


def normalize_temperature_unit(unit: str) -> UnitOfTemperature | str:
    """Normalizes temperature units to UnitOfTemperature, or returns the provided unit."""
    if unit in ["°C", "C", "celsius", "Celsius"]:
        return UnitOfTemperature.CELSIUS
    elif unit in ["°F", "F", "fahrenheit", "Fahrenheit"]:
        return UnitOfTemperature.FAHRENHEIT
    return unit


def to_temperature_map(items: int | dict[str, int] | None) -> dict[str, int]:
    if isinstance(items, dict):
        return {normalize_temperature_unit(k): v for k, v in items.items()}
    return {}
