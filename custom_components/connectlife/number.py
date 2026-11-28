"""Provides number entities for ConnectLife."""

import logging
from homeassistant.components.number import NumberEntity, NumberEntityDescription, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ConnectLifeCoordinator
from .device_mappings import DeviceMappings, DeviceMapping, Property
from .entity import ConnectLifeEntity
from connectlife.appliance import ConnectLifeAppliance
from .utils import climate_bound_properties, device_target_overrides, has_platform, to_unit

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ConnectLife number entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    for appliance in coordinator.data.values():
        mapping = DeviceMappings.get_mapping(appliance)
        overrides = device_target_overrides(config_entry, appliance.device_id)
        climate_bound = climate_bound_properties(appliance, mapping, overrides)
        async_add_entities(
            ConnectLifeNumberEntity(
                coordinator,
                appliance,
                s,
                mapping.properties[s],
                mapping,
            )
            for s in appliance.status_list
            if has_platform(Platform.NUMBER, mapping.properties[s])
            and not mapping.properties[s].local
            and s not in climate_bound
        )
        # Local properties have no status value: created from the mapping, kept in HA.
        async_add_entities(
            ConnectLifeLocalNumberEntity(coordinator, appliance, prop.name, prop, mapping)
            for prop in mapping.properties.values()
            if prop.local and has_platform(Platform.NUMBER, prop)
        )


class ConnectLifeNumberEntity(ConnectLifeEntity, NumberEntity):
    """Number entities for ConnectLife writeable numeric properties."""

    _attr_native_step = 1

    def __init__(
        self,
        coordinator: ConnectLifeCoordinator,
        appliance: ConnectLifeAppliance,
        status: str,
        prop: Property,
        mapping: DeviceMapping,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance, status, Platform.NUMBER)
        self.status = status
        self._unavailable_status = status
        self._unavailable_value = prop.unavailable
        self._available_when = prop.available_when
        self.command_name = (
            prop.number.command_name if prop.number.command_name else status
        )
        device_class = prop.number.device_class
        self.entity_description = NumberEntityDescription(
            key=self._attr_unique_id,
            device_class=device_class,
            entity_registry_visible_default=not prop.hide,
            entity_registry_enabled_default=not prop.optional,
            icon=prop.icon,
            name=status.replace("_", " "),
            native_max_value=prop.number.max_value,  # type: ignore[arg-type]
            native_min_value=prop.number.min_value,  # type: ignore[arg-type]
            native_unit_of_measurement=to_unit(
                prop.number.unit, appliance=appliance, mapping=mapping
            ),
            translation_key=self.to_translation_key(prop.translation_key or status),
            entity_category=prop.entity_category,
        )
        self._refresh_state()

    @callback
    def update_state(self):
        if self.status in self.coordinator.data[self.device_id].status_list:
            value = self.coordinator.data[self.device_id].status_list[self.status]
            self._attr_native_value = value

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        value = int(value)
        _LOGGER.debug("Setting %s to %d on %s", self.status, value, self.nickname)
        await self.async_update_device(
            {self.command_name: value},
            {self.status: value},
        )


class ConnectLifeLocalNumberEntity(ConnectLifeNumberEntity, RestoreNumber):
    """Number kept in HA for a local property.

    Setting it writes nothing to the device: its value is only sent along with commands that include it,
    e.g. a delay sent with the start command.
    """

    def __init__(
        self,
        coordinator: ConnectLifeCoordinator,
        appliance: ConnectLifeAppliance,
        status: str,
        prop: Property,
        mapping: DeviceMapping,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance, status, prop, mapping)
        self._attr_native_value = prop.number.min_value or 0

    async def async_added_to_hass(self) -> None:
        """Restore the last value, and make it available to commands."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self._store()

    @callback
    def update_state(self):
        """The device doesn't report local properties."""

    async def async_set_native_value(self, value: float) -> None:
        """Keep the value, without writing it to the device."""
        self._attr_native_value = int(value)
        self._store()
        self.async_write_ha_state()

    def _store(self) -> None:
        if self._attr_native_value is not None:
            self.coordinator.local_values.setdefault(self.device_id, {})[self.status] = int(self._attr_native_value)
