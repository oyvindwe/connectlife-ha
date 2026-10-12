"""Diagnostics support for ConnectLife."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import dataclasses
from typing import Any

from aiohttp import ClientError
from connectlife.api import ConnectLifeApi, LifeConnectError
from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from connectlife.appliance import ConnectLifeAppliance

from .const import CONF_DEVICES, DOMAIN
from .coordinator import ConnectLifeCoordinator, ConnectLifeStatisticsCoordinator
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
    # The property list is per feature code, so fetch it once for identical appliances.
    property_lists: dict[str, Any] = {}
    return {
        "appliances": [
            await _appliance_diagnostics(hass, entry, coordinator.api, appliance, property_lists)
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
                hass, entry, coordinator.api, coordinator.data[device_id]
            )
    return {}


async def _appliance_diagnostics(
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: ConnectLifeApi,
        appliance: ConnectLifeAppliance,
        property_lists: dict[str, Any] | None = None,
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
        "static_data": await _device_request(appliance, lambda: api.query_static_data(appliance.puid)),
        "system_data": await _device_request(appliance, lambda: api.query_system_data(appliance.puid)),
        "self_check": await _device_request(appliance, lambda: api.get_self_check(appliance.puid)),
        "hour_power": await _device_request(appliance, lambda: api.get_hour_power(appliance.puid)),
        "property_list": await _property_list(api, appliance, {} if property_lists is None else property_lists),
        "statistics": _statistics(hass, entry, appliance, dictionary.statistics_source),
    }, TO_REDACT)


def _statistics(
        hass: HomeAssistant,
        entry: ConfigEntry,
        appliance: ConnectLifeAppliance,
        source: str | None,
) -> dict[str, Any] | None:
    """The last energy statistics fetched for the appliance.

    ``result`` is None when the request failed or returned no data, which makes the
    statistics sensors unavailable.
    """
    if source is None:
        return None
    coordinator: ConnectLifeStatisticsCoordinator | None = hass.data[DOMAIN].get(
        f"{entry.entry_id}_statistics"
    )
    if coordinator is None:
        return {"source": source, "result": None}
    result = (coordinator.data or {}).get(appliance.device_id)
    identifiers = {i for i in (appliance.puid, appliance.device_id, appliance.wifi_id) if i}
    return {
        "source": source,
        "last_update_success": coordinator.last_update_success,
        "result": _redact_values(dataclasses.asdict(result), identifiers) if result else None,
    }


async def _device_request(
        appliance: ConnectLifeAppliance, request: Callable[[], Awaitable[Any]]
) -> Any:
    """The raw response to an undocumented per-device request, or the error.

    Static data lists the settings and values the appliance supports and its firmware
    versions, system data e.g. a dishwasher's programs and their options, self-check the
    faults it can report, and hour power today's hourly energy use. The responses echo
    the appliance's identifiers, so any value equal to one of them is redacted.
    """
    try:
        response = await request()
    except (LifeConnectError, ClientError, TimeoutError) as err:
        return {"error": str(err) or type(err).__name__}
    identifiers = {i for i in (appliance.puid, appliance.device_id, appliance.wifi_id) if i}
    return _redact_values(response, identifiers)


async def _property_list(
        api: ConnectLifeApi, appliance: ConnectLifeAppliance, cache: dict[str, Any]
) -> Any:
    """The feature code's property list: readable/writable, value lists and ranges."""
    key = f"{appliance.device_type_code}-{appliance.device_feature_code}"
    if key not in cache:
        cache[key] = await _device_request(
            appliance,
            lambda: api.get_property_list(appliance.device_type_code, appliance.device_feature_code),
        )
    return cache[key]


def _redact_values(value: Any, identifiers: set[str]) -> Any:
    """Replace every string equal to one of ``identifiers``."""
    if isinstance(value, dict):
        return {k: _redact_values(v, identifiers) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_values(v, identifiers) for v in value]
    if isinstance(value, str) and value in identifiers:
        return REDACTED
    return value
