from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform, UnitOfTemperature

from connectlife.appliance import ConnectLifeAppliance
from .const import TEMPERATURE_UNIT
from .dictionaries import Property, Dictionary


def has_platform(platform: Platform, property: Property):
    return hasattr(property, platform) and not property.disable


def climate_target_bindings(
    appliance: ConnectLifeAppliance, dictionary: Dictionary
) -> dict[str, str]:
    """Resolve which property serves each climate target for this appliance.

    Several properties may declare the same ``climate.target`` (e.g. both
    ``t_swing_angle`` and ``t_up_down`` map to ``swing_mode``). Among the
    candidates the device actually exposes (present in ``status_list`` and not
    disabled), the one with the lowest ``priority`` wins the target; ties are
    broken by dictionary order. Returns ``{target: property_name}``.
    """
    bindings: dict[str, tuple[int, str]] = {}
    for name, prop in dictionary.properties.items():
        if name not in appliance.status_list:
            continue
        if not has_platform(Platform.CLIMATE, prop):
            continue
        target = prop.climate.target
        if target is None:
            continue
        current = bindings.get(target)
        if current is None or prop.climate.priority < current[0]:
            bindings[target] = (prop.climate.priority, name)
    return {target: name for target, (_, name) in bindings.items()}


def climate_bound_properties(
    appliance: ConnectLifeAppliance, dictionary: Dictionary
) -> set[str]:
    """Property names bound to a climate target for this appliance.

    A property that wins a climate target is exposed through the climate entity,
    so its per-property platform (if any) must be suppressed to avoid a
    duplicate entity.
    """
    return set(climate_target_bindings(appliance, dictionary).values())


def to_unit(unit: str | None, appliance: ConnectLifeAppliance, dictionary: Dictionary):
    if unit is None:
        return None
    if unit.startswith("property."):
        unit_property_name = unit[9:]
        if unit_property_name in dictionary.properties:
            unit_value = appliance.status_list[unit_property_name]
            unit_property = dictionary.properties[unit_property_name]
            if has_platform(Platform.CLIMATE, unit_property):
                unit_climate = unit_property.climate
                if unit_climate.target == TEMPERATURE_UNIT and unit_value in unit_climate.options:
                    unit = unit_climate.options[unit_value]
            elif has_platform(Platform.SENSOR, unit_property):
                unit_sensor = unit_property.sensor
                if unit_sensor.device_class == SensorDeviceClass.ENUM and unit_sensor.options is not None and unit_value in unit_sensor.options:
                    unit = unit_sensor.options[unit_value]  # type: ignore[index]
            elif has_platform(Platform.SELECT, unit_property):
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
