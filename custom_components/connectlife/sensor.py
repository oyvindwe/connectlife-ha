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

from .const import DOMAIN
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
            if is_entity(
                Platform.SENSOR,
                dictionary.properties[s],
                appliance.status_list[s],
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
        self.read_only = dd_entry.sensor.read_only
        self.multiplier = dd_entry.sensor.multiplier
        self.unknown_value = dd_entry.sensor.unknown_value

        device_class = dd_entry.sensor.device_class
        self.options_map: dict[int, str] | None = None
        options = None
        if device_class == SensorDeviceClass.ENUM and dd_entry.sensor.options is not None:
            self.options_map = dd_entry.sensor.options
            options = list(self.options_map.values())
        elif device_class is None and isinstance(
            self.coordinator.data[self.device_id].status_list[status], datetime.datetime
        ):
            device_class = SensorDeviceClass.TIMESTAMP
        if device_class == SensorDeviceClass.TIMESTAMP and self.unknown_value is None:
            self.unknown_value = MAX_DATETIME
        state_class = dd_entry.sensor.state_class
        if (
            state_class is None
            and isinstance(
                self.coordinator.data[self.device_id].status_list[status], int
            )
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
            options=options,
            state_class=state_class,
            translation_key=self.to_translation_key(status),
            entity_category=dd_entry.entity_category,
        )
        self.update_state()

    @callback
    def update_state(self):
        if self.status in self.coordinator.data[self.device_id].status_list:
            value = self.coordinator.data[self.device_id].status_list[self.status]
            if self.device_class == SensorDeviceClass.ENUM and self.options_map is not None:
                if value in self.options_map:
                    value = self.options_map[value]
                elif value != self.unknown_value:
                    _LOGGER.warning(
                        "Got unexpected value %d for %s (%s)",
                        value,
                        self.status,
                        self.nickname,
                    )
                    value = None
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
