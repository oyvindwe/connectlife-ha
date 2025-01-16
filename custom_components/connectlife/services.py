"""Services for the Fully Kiosk Browser integration."""

from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.device_registry as dr

from .coordinator import ConnectLifeCoordinator
from .const import DOMAIN

ATTR_ACTION = "action"
SERVICE_SET_ACTION = "set_action"

_LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up the services for the Fully Kiosk Browser integration."""

    async def collect_coordinators(
            device_ids: list[str],
    ) -> dict[str, ConnectLifeCoordinator]:
        config_entries = dict[str, ConfigEntry]()
        registry = dr.async_get(hass)
        for target in device_ids:
            device = registry.async_get(target)
            if device:
                device_entries = dict[str, ConfigEntry]()
                for entry_id in device.config_entries:
                    entry = hass.config_entries.async_get_entry(entry_id)
                    if entry and entry.domain == DOMAIN:
                        for (domain, device_id) in device.identifiers:
                            if domain == DOMAIN:
                                _LOGGER.debug(f"device_id: {device_id}")
                                device_entries[device_id] = entry
                                break
                if not device_entries:
                    raise HomeAssistantError(
                        f"Device '{target}' is not a {DOMAIN} device"
                    )
                config_entries.update(device_entries)
            else:
                raise HomeAssistantError(
                    f"Device '{target}' not found in device registry"
                )
        coordinators = dict[str, ConnectLifeCoordinator]()
        for device_id, config_entry in config_entries.items():
            if config_entry.state != ConfigEntryState.LOADED:
                raise HomeAssistantError(f"{config_entry.title} is not loaded")
            coordinators[device_id] = hass.data[DOMAIN][config_entry.entry_id]
        return coordinators

    async def async_set_action(call: ServiceCall) -> None:
        """Set action on device."""
        coordinators = await collect_coordinators(call.data[ATTR_DEVICE_ID])
        for device_id, coordinator in coordinators.items():
            _LOGGER.debug("Setting Actions to %d on %s", call.data[ATTR_ACTION], device_id)
            # TODO: Consider trigging a data update to avoid waiting for next poll to update state.
            #       Make sure to only do this once per coordinater.
            await coordinator.async_update_device(device_id, {"Actions":  call.data[ATTR_ACTION]}, {})

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ACTION,
        async_set_action,
        schema=vol.Schema(
            vol.All(
                {
                    vol.Required(ATTR_DEVICE_ID): cv.ensure_list,
                    vol.Required(ATTR_ACTION): cv.positive_int,
                }
            )
        ),
    )
