"""Provides a sensor for ConnectLife."""

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
)
from .coordinator import ConnectLifeCoordinator
from .entity import ConnectLifeEntity
from connectlife.appliance import ConnectLifeAppliance

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ConnectLife sensors."""

    api = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = ConnectLifeCoordinator(hass, api)
    await coordinator.async_refresh()

    for appliance in coordinator.appliances.values():
        async_add_entities([ConnectLifeOfflineStateSensor(coordinator, appliance)])
        async_add_entities(
            ConnectLifeStatusSensor(coordinator, appliance, s) for s in appliance.status_list
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.coordinator.appliances[self.device_id].status_list[self.status]
        self.async_write_ha_state()


class ConnectLifeOfflineStateSensor(ConnectLifeEntity, SensorEntity):
    """Sensor class for ConnectLife offline state."""

    def __init__(self, coordinator: ConnectLifeCoordinator, appliance: ConnectLifeAppliance):
        """Initialize the entity."""
        super().__init__(coordinator, appliance)
        self._attr_name = f"{appliance._device_nickname} offline state"
        self._attr_unique_id = f"{appliance.device_id}-offlineState"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.coordinator.appliances[self.device_id].offline_state
        self.async_write_ha_state()
