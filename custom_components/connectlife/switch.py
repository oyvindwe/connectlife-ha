"""Provides a switch for ConnectLife."""

import logging

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from connectlife.appliance import ConnectLifeAppliance

from .const import DOMAIN
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries, Property
from .entity import ConnectLifeEntity
from .utils import is_entity

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
            ConnectLifeSwitch(
                coordinator, appliance, s, dictionary.properties[s], config_entry
            )
            for s in appliance.status_list
            if is_entity(
                Platform.SWITCH, dictionary.properties[s], appliance.status_list[s]
            )
        )


class ConnectLifeSwitch(ConnectLifeEntity, SwitchEntity):
    """Switch class for ConnectLife."""

    def __init__(
        self,
        coordinator: ConnectLifeCoordinator,
        appliance: ConnectLifeAppliance,
        status: str,
        dd_entry: Property,
        config_entry: ConfigEntry,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance, status, Platform.SWITCH, config_entry)
        self.status = status
        self.command_name = (
            dd_entry.switch.command_name if dd_entry.switch.command_name else status
        )
        self.off = dd_entry.switch.off
        self.on = dd_entry.switch.on
        self.command_off = self.off - dd_entry.switch.command_adjust
        self.command_on = self.on - dd_entry.switch.command_adjust
        self.entity_description = SwitchEntityDescription(
            key=self._attr_unique_id,
            entity_registry_visible_default=not dd_entry.hide,
            icon=dd_entry.icon,
            name=status.replace("_", " "),
            translation_key=self.to_translation_key(status),
            device_class=dd_entry.switch.device_class,
            entity_category=dd_entry.entity_category,
        )
        self.update_state()

    @callback
    def update_state(self):
        if self.status in self.coordinator.data[self.device_id].status_list:
            value = self.coordinator.data[self.device_id].status_list[self.status]
            if value == self.on:
                self._attr_is_on = True
            elif value == self.off:
                self._attr_is_on = False
            else:
                self._attr_is_on = None
                _LOGGER.warning("Unknown value %s for %s", str(value), self.status)
        self._attr_available = self.coordinator.data[self.device_id].offline_state == 1

    async def async_turn_off(self, **kwargs):
        """Turn off."""
        await self.async_update_device(
            {self.command_name: self.command_off},
            {self.status: self.off},
        )

    async def async_turn_on(self, **kwargs):
        """Turn on."""
        await self.async_update_device(
            {self.command_name: self.command_on}, {self.status: self.on}
        )
