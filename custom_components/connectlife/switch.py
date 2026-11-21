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
from .device_mappings import DeviceMappings, Property
from .entity import ConnectLifeEntity
from .utils import climate_bound_properties, device_target_overrides, has_platform

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ConnectLife sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    for appliance in coordinator.data.values():
        mapping = DeviceMappings.get_mapping(appliance)
        overrides = device_target_overrides(config_entry, appliance.device_id)
        climate_bound = climate_bound_properties(appliance, mapping, overrides)
        async_add_entities(
            ConnectLifeSwitch(
                coordinator, appliance, s, mapping.properties[s]
            )
            for s in appliance.status_list
            if has_platform(Platform.SWITCH, mapping.properties[s])
            and s not in climate_bound
        )


class ConnectLifeSwitch(ConnectLifeEntity, SwitchEntity):
    """Switch class for ConnectLife."""

    def __init__(
        self,
        coordinator: ConnectLifeCoordinator,
        appliance: ConnectLifeAppliance,
        status: str,
        prop: Property,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance, status, Platform.SWITCH)
        self.status = status
        self._unavailable_status = status
        self._unavailable_value = prop.unavailable
        self._available_when = prop.available_when
        self.command_name = (
            prop.switch.command_name if prop.switch.command_name else status
        )
        self.off = prop.switch.off
        self.on = prop.switch.on
        self.command_off = self.off - prop.switch.command_adjust
        self.command_on = self.on - prop.switch.command_adjust
        self.entity_description = SwitchEntityDescription(
            key=self._attr_unique_id,
            entity_registry_visible_default=not prop.hide,
            entity_registry_enabled_default=not prop.optional,
            icon=prop.icon,
            name=status.replace("_", " "),
            translation_key=self.to_translation_key(prop.translation_key or status),
            device_class=prop.switch.device_class,
            entity_category=prop.entity_category,
        )
        self._refresh_state()

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
