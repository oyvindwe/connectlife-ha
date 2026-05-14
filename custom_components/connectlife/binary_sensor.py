"""Provides a binary sensor for ConnectLife."""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries, Property
from .entity import ConnectLifeEntity
from connectlife.appliance import ConnectLifeAppliance
from .utils import has_platform

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ConnectLife sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    for appliance in coordinator.data.values():
        dictionary = Dictionaries.get_dictionary(appliance)
        async_add_entities(
            ConnectLifeBinaryStatusSensor(
                coordinator, appliance, s, dictionary.properties[s]
            )
            for s in appliance.status_list
            if has_platform(Platform.BINARY_SENSOR, dictionary.properties[s])
        )


class ConnectLifeBinaryStatusSensor(ConnectLifeEntity, BinarySensorEntity):
    """Sensor class for ConnectLife arbitrary status."""

    def __init__(
        self,
        coordinator: ConnectLifeCoordinator,
        appliance: ConnectLifeAppliance,
        status: str,
        dd_entry: Property,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance, status, Platform.BINARY_SENSOR)
        self.status = status
        self._unavailable_status = status
        self._unavailable_value = dd_entry.unavailable
        self.options = dd_entry.binary_sensor.options
        self.entity_description = BinarySensorEntityDescription(
            key=self._attr_unique_id,
            entity_registry_visible_default=not dd_entry.hide,
            entity_registry_enabled_default=not dd_entry.optional,
            icon=dd_entry.icon,
            name=status.replace("_", " "),
            translation_key=self.to_translation_key(status),
            device_class=dd_entry.binary_sensor.device_class,
            entity_category=dd_entry.entity_category,
        )
        self._refresh_state()

    @callback
    def update_state(self):
        if self.status in self.coordinator.data[self.device_id].status_list:
            value = self.coordinator.data[self.device_id].status_list[self.status]
            if value in self.options:
                self._attr_is_on = self.options[value]
            else:
                self._attr_is_on = None
                _LOGGER.warning("Unknown value %d for %s", value, self.status)
