"""The ConnectLife integration."""

from __future__ import annotations

import logging

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from connectlife.api import LifeConnectAuthError, LifeConnectError

from .client import create_api
from .const import (
    CONF_DEVELOPMENT_MODE,
    CONF_TEST_SERVER_URL,
    CONF_TRIR,
    DATA_STATE_CLASS_MIGRATION_DONE,
    DOMAIN,
)
from .coordinator import ConnectLifeCoordinator, ConnectLifeEnergyCoordinator
from .dictionaries import Dictionaries
from .services import async_setup_services
from .statistics_sources import enabled_sensors

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.HUMIDIFIER,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up ConnectLife."""

    await async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ConnectLife from a config entry."""
    _LOGGER.debug("Setting up ConnectLife")
    _LOGGER.debug("Options: %s", entry.options)
    hass.data.setdefault(DOMAIN, {})
    test_server_url = (
        entry.options.get(CONF_TEST_SERVER_URL)
       if entry.options.get(CONF_DEVELOPMENT_MODE)
        else None
    )
    api = create_api(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        trir=entry.data.get(CONF_TRIR, False),
        test_server_url=test_server_url,
    )
    try:
        await api.login()
    except LifeConnectAuthError as ex:
        raise ConfigEntryAuthFailed from ex
    except LifeConnectError as ex:
        raise ConfigEntryNotReady from ex
    coordinator = ConnectLifeCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Only create the statistics coordinator if some device opts into a statistics
    # endpoint with at least one sensor enabled (otherwise it would poll nothing).
    has_statistics = any(
        enabled_sensors(
            Dictionaries.get_dictionary(appliance).statistics_source,
            Dictionaries.get_dictionary(appliance).statistics_sensors,
        )
        for appliance in coordinator.data.values()
    )
    if has_statistics:
        energy_coordinator = ConnectLifeEnergyCoordinator(hass, api, coordinator)
        await energy_coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][f"{entry.entry_id}_energy"] = energy_coordinator

    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.cleanup_removed_entities()
    if not entry.data.get(DATA_STATE_CLASS_MIGRATION_DONE):
        await coordinator.update_orphaned_statistics_issue()

    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug(f"Reloading ConnectLife")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug(f"Unloading ConnectLife")

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_energy", None)

    return unload_ok
