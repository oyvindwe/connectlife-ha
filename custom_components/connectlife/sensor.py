"""Provides a sensor for ConnectLife."""

import datetime
import logging
import voluptuous as vol
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SW_VERSION_PROPERTY
from .coordinator import ConnectLifeCoordinator, ConnectLifeEnergyCoordinator
from .dictionaries import Dictionaries, Dictionary, Property
from .entity import ConnectLifeEntity
from connectlife.appliance import ConnectLifeAppliance, MAX_DATETIME
from .utils import has_platform, to_unit

SERVICE_SET_VALUE = "set_value"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ConnectLife sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    energy_coordinator = hass.data[DOMAIN][f"{config_entry.entry_id}_energy"]
    for appliance in coordinator.data.values():
        dictionary = Dictionaries.get_dictionary(appliance)
        async_add_entities(
            ConnectLifeStatusSensor(
                coordinator, appliance, s, dictionary.properties[s], dictionary
            )
            for s in appliance.status_list
            if s != SW_VERSION_PROPERTY
            and has_platform(Platform.SENSOR, dictionary.properties[s])
        )
        async_add_entities(
            ConnectLifeStatusSensor(
                coordinator, appliance, name, prop, dictionary
            )
            for name, prop in dictionary.properties.items()
            if prop.combine
            and name not in appliance.status_list
            and hasattr(prop, Platform.SENSOR)
            and any(
                src["property"] in appliance.status_list
                for src in prop.combine
            )
        )
    async_add_entities(
        ConnectLifeEnergySensor(coordinator, energy_coordinator, appliance)
        for appliance in coordinator.data.values()
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_VALUE,
        {vol.Required("value"): cv.positive_int},
        "async_set_value",
    )


class ConnectLifeStatusSensor(ConnectLifeEntity, SensorEntity):
    """Sensor class for ConnectLife arbitrary status."""

    def __init__(
        self,
        coordinator: ConnectLifeCoordinator,
        appliance: ConnectLifeAppliance,
        status: str,
        dd_entry: Property,
        dictionary: Dictionary,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance, status, Platform.SENSOR)
        self.status = status
        self._unavailable_status = status
        self._unavailable_value = dd_entry.unavailable
        self.combine = dd_entry.combine
        self.read_only = True if self.combine else dd_entry.sensor.read_only
        self.multiplier = dd_entry.sensor.multiplier
        self.unknown_value = dd_entry.sensor.unknown_value

        device_class = dd_entry.sensor.device_class
        self.options_map: dict[int, str] | None = None
        current_value = self.coordinator.data[self.device_id].status_list.get(status)
        if device_class == SensorDeviceClass.ENUM and dd_entry.sensor.options is not None:
            # Copy: unmapped values are added per-entity, avoid leaking to other appliances.
            self.options_map = dict(dd_entry.sensor.options)
            self._attr_options = list(self.options_map.values())
        elif device_class is None and isinstance(current_value, datetime.datetime):
            device_class = SensorDeviceClass.TIMESTAMP
        if device_class == SensorDeviceClass.TIMESTAMP and self.unknown_value is None:
            self.unknown_value = MAX_DATETIME
        state_class = dd_entry.sensor.state_class
        self.entity_description = SensorEntityDescription(
            key=self._attr_unique_id,
            device_class=device_class,
            entity_registry_visible_default=not dd_entry.hide,
            entity_registry_enabled_default=not dd_entry.optional,
            icon=dd_entry.icon,
            name=status.replace("_", " "),
            native_unit_of_measurement=to_unit(
                dd_entry.sensor.unit, appliance=appliance, dictionary=dictionary
            ),
            state_class=state_class,
            translation_key=self.to_translation_key(status),
            entity_category=dd_entry.entity_category,
        )
        self._refresh_state()

    @callback
    def update_state(self):
        status_list = self.coordinator.data[self.device_id].status_list
        if self.combine:
            value = 0.0
            has_sources = False
            for source in self.combine:
                src_value = status_list.get(source["property"])
                if src_value is not None and isinstance(src_value, (int, float)):
                    if "unknown_value" in source and src_value == source["unknown_value"]:
                        continue
                    value += src_value * source.get("multiplier", 1)
                    has_sources = True
            if has_sources:
                if value == self.unknown_value:
                    self._attr_native_value = None
                else:
                    if self.multiplier is not None:
                        value *= self.multiplier
                    self._attr_native_value = value
                return
            elif self.status not in status_list:
                self._attr_native_value = None
                return
        if self.status in status_list:
            value = status_list[self.status]
            if self.device_class == SensorDeviceClass.ENUM and self.options_map is not None:
                if value in self.options_map:
                    value = self.options_map[value]
                elif value != self.unknown_value:
                    str_value = str(value)
                    if self._attr_options is not None and str_value not in self._attr_options:
                        _LOGGER.warning(
                            "Got unexpected value %s for %s (%s)",
                            str_value,
                            self.status,
                            self.nickname,
                        )
                        self.options_map[value] = str_value
                        self._attr_options = [*self._attr_options, str_value]
                    value = str_value
            if value == self.unknown_value:
                self._attr_native_value = None
            else:
                if self.multiplier is not None and value is not None:
                    value *= self.multiplier  # type: ignore[operator]
                self._attr_native_value = value

    async def async_set_value(self, value: int) -> None:
        """Set value for this sensor."""
        _LOGGER.debug("Setting %s to %d on %s", self.status, value, self.nickname)
        if self.read_only is None:
            _LOGGER.warning(
                "%s may be read-only on %s", self.entity_description.name, self.nickname
            )
        elif self.read_only:
            raise ServiceValidationError(
                f"{self.entity_description.name} is read-only on {self.nickname}"
            )
        await self.async_update_device({self.status: value})


class ConnectLifeEnergySensor(CoordinatorEntity[ConnectLifeEnergyCoordinator], SensorEntity):
    """Sensor for daily energy consumption from the ConnectLife energy endpoint."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_translation_key = "daily_energy_kwh"

    def __init__(
        self,
        appliance_coordinator: ConnectLifeCoordinator,
        energy_coordinator: ConnectLifeEnergyCoordinator,
        appliance: ConnectLifeAppliance,
    ):
        """Initialize the energy sensor."""
        super().__init__(energy_coordinator)
        self._device_id = appliance.device_id
        self._appliance_coordinator = appliance_coordinator
        self._attr_unique_id = f"{appliance.device_id}-daily_energy_kwh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, appliance.device_id)},
        )
        appliance_coordinator.add_entity(self._attr_unique_id, Platform.SENSOR)
        self._update_native_value()

    @property
    def available(self) -> bool:
        appliance = self._appliance_coordinator.data.get(self._device_id)
        return (
            super().available
            and appliance is not None
            and appliance.offline_state == 1
            and self.coordinator.data is not None
            and self.coordinator.data.get(self._device_id) is not None
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the energy coordinator."""
        self._update_native_value()
        self.async_write_ha_state()

    def _update_native_value(self) -> None:
        """Update native value from energy coordinator data."""
        if self.coordinator.data and self._device_id in self.coordinator.data:
            self._attr_native_value = self.coordinator.data[self._device_id]
        else:
            self._attr_native_value = None
