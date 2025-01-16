"""The ConnectLife integration."""

from __future__ import annotations

from homeassistant.exceptions import ConfigEntryError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from connectlife.api import ConnectLifeApi, LifeConnectAuthError

from .const import CONF_DEVELOPMENT_MODE, CONF_TEST_SERVER_URL, DOMAIN
from .coordinator import ConnectLifeCoordinator
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.HUMIDIFIER,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up ConnectLife."""

    await async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ConnectLife from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    test_server_url = (
        entry.options.get(CONF_TEST_SERVER_URL)
       if entry.options.get(CONF_DEVELOPMENT_MODE)
        else None
    )
    api = ConnectLifeApi(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], test_server_url)
    try:
        await api.login()
    except LifeConnectAuthError as ex:
        raise ConfigEntryError from ex
    coordinator = ConnectLifeCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.cleanup_removed_entities()

    return True

async def update_listener(hass, entry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
