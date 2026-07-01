from collections.abc import Mapping

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform, UnitOfTemperature

from connectlife.appliance import ConnectLifeAppliance
from .const import CONF_DEVICES, CONF_TARGET_OVERRIDES, TEMPERATURE_UNIT
from .dictionaries import Property, Dictionary


def has_platform(platform: Platform, property: Property):
    return hasattr(property, platform) and not property.disable


def _climate_candidates(
    appliance: ConnectLifeAppliance, dictionary: Dictionary
) -> dict[str, list[tuple[int, str]]]:
    """Group the climate-target candidates the appliance actually exposes.

    Returns ``{target: [(priority, property_name), ...]}`` in dictionary order,
    including only properties present in ``status_list`` and not disabled.
    """
    candidates: dict[str, list[tuple[int, str]]] = {}
    for name, prop in dictionary.properties.items():
        if name not in appliance.status_list:
            continue
        if not has_platform(Platform.CLIMATE, prop):
            continue
        target = prop.climate.target
        if target is None:
            continue
        candidates.setdefault(target, []).append((prop.climate.priority, name))
    return candidates


def climate_target_bindings(
    appliance: ConnectLifeAppliance,
    dictionary: Dictionary,
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve which property serves each climate target for this appliance.

    Several properties may declare the same ``climate.target`` (e.g. both
    ``t_swing_angle`` and ``t_up_down`` map to ``swing_mode``). Among the
    candidates the device actually exposes (present in ``status_list`` and not
    disabled), the one with the lowest ``priority`` wins the target; ties are
    broken by dictionary order. Returns ``{target: property_name}``.

    ``overrides`` (``{target: property_name}``) lets the user pin a specific
    candidate for a target — used when a device advertises a control it doesn't
    actually support (e.g. ``t_swing_angle`` present but inert). An override is
    honoured only when the named property is itself a valid candidate for that
    target on this device; otherwise the automatic winner is kept.
    """
    overrides = overrides or {}
    bindings: dict[str, str] = {}
    for target, candidates in _climate_candidates(appliance, dictionary).items():
        names = [name for _, name in candidates]
        override = overrides.get(target)
        if override in names:
            bindings[target] = override
        else:
            # Lowest priority wins; min() keeps the first on ties (dict order).
            bindings[target] = min(candidates, key=lambda c: c[0])[1]
    return bindings


def contested_climate_targets(
    appliance: ConnectLifeAppliance, dictionary: Dictionary
) -> dict[str, list[str]]:
    """Climate targets this appliance exposes more than one candidate for.

    These are the targets where the automatic binding makes a choice the user
    may want to override. Returns ``{target: [property_name, ...]}`` (dictionary
    order), only for targets with two or more candidates.
    """
    return {
        target: [name for _, name in candidates]
        for target, candidates in _climate_candidates(appliance, dictionary).items()
        if len(candidates) > 1
    }


def device_target_overrides(config_entry, device_id: str) -> dict[str, str]:
    """Per-device climate target overrides configured via the options flow."""
    device = config_entry.options.get(CONF_DEVICES, {}).get(device_id, {})
    return device.get(CONF_TARGET_OVERRIDES, {})


def climate_bound_properties(
    appliance: ConnectLifeAppliance,
    dictionary: Dictionary,
    overrides: Mapping[str, str] | None = None,
) -> set[str]:
    """Property names bound to a climate target for this appliance.

    A property that wins a climate target is exposed through the climate entity,
    so its per-property platform (if any) must be suppressed to avoid a
    duplicate entity.
    """
    return set(climate_target_bindings(appliance, dictionary, overrides).values())


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
