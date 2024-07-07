"""Provides a binary sensor for ConnectLife."""
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
)
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries, Property
from .entity import ConnectLifeEntity
from connectlife.appliance import ConnectLifeAppliance

_LOGGER = logging.getLogger(__name__)

VALUES = {0: False, 1: False, 2: True}


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ConnectLife sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    for appliance in coordinator.appliances.values():
        dictionary = Dictionaries.get_dictionary(appliance)
        async_add_entities(
            ConnectLifeBinaryStatusSensor(coordinator, appliance, s, dictionary[s])
            for s in appliance.status_list if hasattr(dictionary[s], Platform.BINARY_SENSOR)
        )


class ConnectLifeBinaryStatusSensor(ConnectLifeEntity, BinarySensorEntity):
    """Sensor class for ConnectLife arbitrary status."""

    def __init__(
            self,
            coordinator: ConnectLifeCoordinator,
            appliance: ConnectLifeAppliance,
            status: str,
            dd_entry: Property
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance)
        self._attr_unique_id = f"{appliance.device_id}-{status}"
        self.status = status
        self.entity_description = BinarySensorEntityDescription(
            key=self._attr_unique_id,
            entity_registry_visible_default=not dd_entry.hide,
            icon=dd_entry.icon,
            name=status.replace("_", " "),
            translation_key=status,
            device_class=dd_entry.binary_sensor.device_class
        )
        self.update_state()

    @callback
    def update_state(self):
        if self.status in self.coordinator.appliances[self.device_id].status_list:
            value = self.coordinator.appliances[self.device_id].status_list[self.status]
            if value in VALUES:
                self._attr_is_on = VALUES[value]
            else:
                self._attr_is_on = None
                _LOGGER.warning("Unknown value %d for %s", value, self.status)
        self._attr_available = self.coordinator.appliances[self.device_id].offline_state == 1
