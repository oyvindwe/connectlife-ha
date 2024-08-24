"""Provides a selector for ConnectLife."""
import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
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


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ConnectLife selectors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    for appliance in coordinator.data.values():
        dictionary = Dictionaries.get_dictionary(appliance)
        async_add_entities(
            ConnectLifeSelect(coordinator, appliance, s, dictionary.properties[s], config_entry)
            for s in appliance.status_list if hasattr(dictionary.properties[s], Platform.SELECT) and not dictionary.properties[s].disable
        )


class ConnectLifeSelect(ConnectLifeEntity, SelectEntity):
    """Select class for ConnectLife."""

    _attr_current_option = None

    def __init__(
            self,
            coordinator: ConnectLifeCoordinator,
            appliance: ConnectLifeAppliance,
            status: str,
            dd_entry: Property,
            config_entry: ConfigEntry,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance, config_entry)
        self._attr_unique_id = f"{appliance.device_id}-{status}"
        self.status = status
        self.options_map = dd_entry.select.options
        self.reverse_options_map = {v: k for k, v in self.options_map.items()}
        self.entity_description = SelectEntityDescription(
            key=self._attr_unique_id,
            entity_registry_visible_default=not dd_entry.hide,
            icon=dd_entry.icon,
            name=status.replace("_", " "),
            translation_key=status,
            options=list(self.options_map.values())
        )
        self.update_state()

    @callback
    def update_state(self):
        if self.status in self.coordinator.data[self.device_id].status_list:
            value = self.coordinator.data[self.device_id].status_list[self.status]
            if value in self.options_map:
                value = self.options_map[value]
            else:
                _LOGGER.warning("Got unexpected value %d for %s (%s)", value, self.status, self.nickname)
                _value = None
            self._attr_current_option = value

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.async_update_device({self.status: self.reverse_options_map[option]})
