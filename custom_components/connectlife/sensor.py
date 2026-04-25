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
from connectlife.api import LifeConnectError
from connectlife.appliance import ConnectLifeAppliance, MAX_DATETIME
from .utils import is_entity, to_unit

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
            and is_entity(
                Platform.SENSOR,
                dictionary.properties[s],
                appliance.status_list[s],
            )
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
        if (
            state_class is None
            and not dd_entry.sensor.state_class_explicit
            and (isinstance(current_value, int) or self.combine)
            and device_class != SensorDeviceClass.ENUM
        ):
            state_class = SensorStateClass.MEASUREMENT
        self.entity_description = SensorEntityDescription(
            key=self._attr_unique_id,
            device_class=device_class,
            entity_registry_visible_default=not dd_entry.hide,
            icon=dd_entry.icon,
            name=status.replace("_", " "),
            native_unit_of_measurement=to_unit(
                dd_entry.sensor.unit, appliance=appliance, dictionary=dictionary
            ),
            state_class=state_class,
            translation_key=self.to_translation_key(status),
            entity_category=dd_entry.entity_category,
        )
        self.update_state()

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
                self._attr_available = self.coordinator.data[self.device_id].offline_state == 1
                return
            elif self.status not in status_list:
                self._attr_native_value = None
                self._attr_available = self.coordinator.data[self.device_id].offline_state == 1
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
        self._attr_available = self.coordinator.data[self.device_id].offline_state == 1

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
        try:
            await self.async_update_device({self.status: value})
        except LifeConnectError as api_error:
            raise ServiceValidationError(str(api_error)) from api_error


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
        self._attr_unique_id = f"{appliance.device_id}-daily_energy_kwh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, appliance.device_id)},
        )
        appliance_coordinator.add_entity(self._attr_unique_id, Platform.SENSOR)
        self._update_native_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the energy coordinator."""
        self._update_native_value()
        self.async_write_ha_state()

    def _update_native_value(self) -> None:
        """Update native value from energy coordinator data."""
        if self.coordinator.data and self._device_id in self.coordinator.data:
            value = self.coordinator.data[self._device_id]
            self._attr_native_value = value
            self._attr_available = value is not None
        else:
            self._attr_native_value = None
            self._attr_available = False
