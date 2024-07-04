"""Provides a sensor for ConnectLife."""

import logging
import voluptuous as vol
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import config_validation as cv, entity_platform, service

from .const import (
    DOMAIN,
)
from .coordinator import ConnectLifeCoordinator
from .entity import ConnectLifeEntity
from connectlife.appliance import ConnectLifeAppliance

SERVICE_SET_VALUE = "set_value"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ConnectLife sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    for appliance in coordinator.appliances.values():
        async_add_entities(
            ConnectLifeStatusSensor(coordinator, appliance, s) for s in appliance.status_list
        )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_VALUE,
        {vol.Required("value"): cv.positive_int},
        "async_set_value",
    )


class ConnectLifeStatusSensor(ConnectLifeEntity, SensorEntity):
    """Sensor class for ConnectLife arbitrary status."""

    def __init__(self, coordinator: ConnectLifeCoordinator, appliance: ConnectLifeAppliance, status: str):
        """Initialize the entity."""
        super().__init__(coordinator, appliance)
        self.status = status
        description = status.replace("_", " ")
        self._attr_name = f"{appliance._device_nickname} {description}"
        self._attr_unique_id = f"{appliance.device_id}-{status}"
        self.update_state()

    @callback
    def update_state(self):
        if self.status in self.coordinator.appliances[self.device_id].status_list:
            self._attr_native_value = self.coordinator.appliances[self.device_id].status_list[self.status]
        self._attr_available = self.coordinator.appliances[self.device_id]._offline_state == 1

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update_state()
        self.async_write_ha_state()

    async def async_set_value(self, value: int) -> None:
        """Set value for this sensor."""
        _LOGGER.debug("Setting %s to %d", self.status, value)
        await self.coordinator.api.update_appliance(self.puid, {self.status: str(value)})
