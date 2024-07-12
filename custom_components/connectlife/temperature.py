from homeassistant.const import UnitOfTemperature


def to_unit_of_temperature(temp: str) -> UnitOfTemperature | None:
    if temp in ["°C", "C", "celsius", "Celsius"]:
        return UnitOfTemperature.CELSIUS
    elif temp in ["°F", "F", "fahrenheit", "Fahrenheit"]:
        return UnitOfTemperature.FAHRENHEIT
    else:
        return None


def to_temperature_map(items: dict[str, int] | None) -> dict[UnitOfTemperature, int] | None:
    return {to_unit_of_temperature(k): v for k, v in items.items()} if items else None
