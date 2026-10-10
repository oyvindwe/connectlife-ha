"""Diagnostics support for ConnectLife."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
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
    "deviceNickName",
    "ip",
    "mac",
    "puid",
    "roomName",
    "serial",
    "ssid",
    "wifiId",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for all appliances of a config entry."""
    coordinator: ConnectLifeCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "appliances": [
            _appliance_diagnostics(entry, appliance)
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
            return _appliance_diagnostics(entry, coordinator.data[device_id])
    return {}


def _appliance_diagnostics(entry: ConfigEntry, appliance: ConnectLifeAppliance) -> dict[str, Any]:
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
    }, TO_REDACT)
