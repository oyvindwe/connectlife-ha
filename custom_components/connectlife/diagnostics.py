"""Diagnostics support for ConnectLife."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError
from connectlife.api import ConnectLifeApi, LifeConnectError
from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from connectlife.appliance import ConnectLifeAppliance

from .const import CONF_DEVICES, DOMAIN
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries, _load_yaml
from .statistics_sources import enabled_sensors

# Identifiers and names are left out of the report altogether. This is a safety
# net in case an appliance reports something private in its status list.
TO_REDACT = {
    "deviceId",
    "device_id",
    "deviceNickName",
    "ip",
    "mac",
    "puid",
    "roomName",
    "serial",
    "ssid",
    "wifiId",
    "wifi_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for all appliances of a config entry."""
    coordinator: ConnectLifeCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "appliances": [
            await _appliance_diagnostics(entry, coordinator.api, appliance)
            for appliance in coordinator.data.values()
        ],
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for one appliance."""
    coordinator: ConnectLifeCoordinator = hass.data[DOMAIN][entry.entry_id]
    for domain, device_id in device.identifiers:
        if domain == DOMAIN and device_id in coordinator.data:
            return await _appliance_diagnostics(
                entry, coordinator.api, coordinator.data[device_id]
            )
    return {}


async def _appliance_diagnostics(
        entry: ConfigEntry, api: ConnectLifeApi, appliance: ConnectLifeAppliance
) -> dict[str, Any]:
    """Appliance status and how it is mapped, without device IDs or names."""
    type_code = appliance.device_type_code
    feature_code = appliance.device_feature_code
    dictionary = Dictionaries.get_dictionary(appliance)
    # Unmapped properties resolve to the dictionary's default entry, whose name
    # does not match the status key.
    unmapped = sorted(
        name
        for name in appliance.status_list
        if (prop := dictionary.properties.get(name)) is None or prop.name != name
    )
    return async_redact_data({
        "device_type_code": type_code,
        "device_type_name": appliance.device_type_name,
        "device_feature_code": feature_code,
        "device_feature_name": appliance.device_feature_name,
        "offline_state": appliance.offline_state,
        "mapping_files": {
            f"{type_code}.yaml": _load_yaml(f"data_dictionaries/{type_code}.yaml")[0],
            f"{type_code}-{feature_code}.yaml": _load_yaml(
                f"data_dictionaries/{type_code}-{feature_code}.yaml"
            )[0],
        },
        "statistics_sensors": [
            sensor.key
            for sensor in enabled_sensors(
                dictionary.statistics_source, dictionary.statistics_sensors
            )
        ],
        "options": entry.options.get(CONF_DEVICES, {}).get(appliance.device_id, {}),
        "unmapped_properties": unmapped,
        "status_list": appliance.status_list,
        "static_data": await _static_data(api, appliance),
    }, TO_REDACT)


async def _static_data(api: ConnectLifeApi, appliance: ConnectLifeAppliance) -> Any:
    """The appliance's static data: the settings and values it supports, and its firmware versions.

    The response is undocumented and echoes the appliance's identifiers, so any
    value equal to one of them is redacted as well.
    """
    try:
        static_data = await api.query_static_data(appliance.puid)
    except (LifeConnectError, ClientError, TimeoutError) as err:
        return {"error": str(err) or type(err).__name__}
    identifiers = {i for i in (appliance.puid, appliance.device_id, appliance.wifi_id) if i}
    return _redact_values(static_data, identifiers)


def _redact_values(value: Any, identifiers: set[str]) -> Any:
    """Replace every string equal to one of ``identifiers``."""
    if isinstance(value, dict):
        return {k: _redact_values(v, identifiers) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_values(v, identifiers) for v in value]
    if isinstance(value, str) and value in identifiers:
        return REDACTED
    return value
