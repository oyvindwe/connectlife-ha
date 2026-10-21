"""The ConnectLife integration."""

from __future__ import annotations

import logging

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow, config_validation as cv
from homeassistant.helpers.typing import ConfigType
from connectlife.api import (
    LifeConnectAuthError,
    LifeConnectError,
    LifeConnectTermsNotAcceptedError,
)

from .client import create_api
from .const import (
    AUTH_TYPE_OAUTH,
    CONF_AUTH_TYPE,
    CONF_DEVELOPMENT_MODE,
    CONF_TEST_SERVER_URL,
    CONF_TRIR,
    DATA_STATE_CLASS_MIGRATION_DONE,
    DOMAIN,
)
from .coordinator import ConnectLifeCoordinator, ConnectLifeStatisticsCoordinator
from .dictionaries import Dictionaries
from .oauth import ConnectLifeOAuth2Implementation, create_oauth_api
from .services import async_setup_services
from .statistics_sources import enabled_sensors
from .terms import terms_accepted, terms_not_accepted, terms_retry_throttled

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
    config_entry_oauth2_flow.async_register_implementation(
        hass, DOMAIN, ConnectLifeOAuth2Implementation(hass)
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ConnectLife from a config entry."""
    _LOGGER.debug("Setting up ConnectLife")
    _LOGGER.debug("Options: %s", entry.options)
    hass.data.setdefault(DOMAIN, {})
    if entry.data.get(CONF_AUTH_TYPE) == AUTH_TYPE_OAUTH:
        implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
        api = create_oauth_api(
            entry, config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
        )
    else:
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
    if terms_retry_throttled(hass, entry):
        _LOGGER.debug("Terms & Conditions not accepted recently, skipping login")
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="terms_not_accepted"
        )
    try:
        await api.login()
    except LifeConnectTermsNotAcceptedError as ex:
        # Re-entering credentials can't fix this, so retry setup (throttled)
        # instead of starting reauth; it recovers once the terms are accepted.
        terms_not_accepted(hass, entry)
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="terms_not_accepted"
        ) from ex
    except LifeConnectAuthError as ex:
        raise ConfigEntryAuthFailed(str(ex)) from ex
    except LifeConnectError as ex:
        raise ConfigEntryNotReady(str(ex)) from ex
    terms_accepted(hass, entry)
    coordinator = ConnectLifeCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Only create the statistics coordinator if some device opts into a statistics
    # endpoint with at least one sensor enabled (otherwise it would poll nothing).
    has_statistics = any(
        enabled_sensors(d.statistics_source, d.statistics_sensors)
        for appliance in coordinator.data.values()
        if (d := Dictionaries.get_dictionary(appliance))
    )
    if has_statistics:
        statistics_coordinator = ConnectLifeStatisticsCoordinator(hass, api, coordinator)
        await statistics_coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][f"{entry.entry_id}_statistics"] = statistics_coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.cleanup_removed_entities()
    if not entry.data.get(DATA_STATE_CLASS_MIGRATION_DONE):
        await coordinator.update_orphaned_statistics_issue()

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug(f"Unloading ConnectLife")

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_statistics", None)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry."""
    # Status properties seen per device; kept across reloads (see coordinator).
    hass.data.get(DOMAIN, {}).pop(f"{entry.entry_id}_status_keys", None)
