"""Provides a sensor for ConnectLife."""
import datetime
import logging
import voluptuous as vol
from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import config_validation as cv, entity_platform, service

from .const import (
    DOMAIN,
)
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries, Property
from .entity import ConnectLifeEntity
from connectlife.api import LifeConnectError
from connectlife.appliance import ConnectLifeAppliance

SERVICE_SET_VALUE = "set_value"

_LOGGER = logging.getLogger(__name__)


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
            ConnectLifeStatusSensor(coordinator, appliance, s, dictionary[s])
            for s in appliance.status_list if hasattr(dictionary[s], Platform.SENSOR)
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
            dd_entry: Property
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance)
        self._attr_unique_id = f"{appliance.device_id}-{status}"
        self.status = status
        self.writable = dd_entry.sensor.writable
        self.max_value = dd_entry.sensor.max_value
        self.unknown_value = dd_entry.sensor.unknown_value
        device_class = dd_entry.sensor.device_class
        options = None
        if device_class == SensorDeviceClass.ENUM:
            self.options_map = dd_entry.sensor.options
            options = list(self.options_map.values())
        elif (device_class is None
              and isinstance(self.coordinator.appliances[self.device_id].status_list[status], datetime.datetime)):
            device_class = SensorDeviceClass.TIMESTAMP
        state_class = dd_entry.sensor.state_class
        if (state_class is None
                and isinstance(self.coordinator.appliances[self.device_id].status_list[status], int)
                and device_class != SensorDeviceClass.ENUM):
            state_class = SensorStateClass.MEASUREMENT
        self.entity_description = SensorEntityDescription(
            key=self._attr_unique_id,
            device_class=device_class,
            entity_registry_visible_default=not dd_entry.hide,
            icon=dd_entry.icon,
            name=status.replace("_", " "),
            native_unit_of_measurement=dd_entry.sensor.unit,
            options=options,
            state_class=state_class,
            translation_key=status,
        )
        self.update_state()

    @callback
    def update_state(self):
        if self.status in self.coordinator.appliances[self.device_id].status_list:
            value = self.coordinator.appliances[self.device_id].status_list[self.status]
            if self.device_class == SensorDeviceClass.ENUM:
                if value in self.options_map:
                    value = self.options_map[value]
                else:
                    _LOGGER.warning("Got unexpected value %d for %s", value, self.status)
                    value = None
            self._attr_native_value = value if value != self.unknown_value else None
        self._attr_available = self.coordinator.appliances[self.device_id].offline_state == 1

    async def async_set_value(self, value: int) -> None:
        """Set value for this sensor."""
        _LOGGER.debug("Setting %s to %d", self.status, value)
        if self.writable is None:
            _LOGGER.warning("%s may not be writable", self._attr_name)
        elif not self.writable:
            raise ServiceValidationError(f"{self._attr_name} is read only")
        if self.max_value is not None and value > self.max_value:
            raise ServiceValidationError(f"Max value for {self._attr_name} is {self.max_value}")
        try:
            await self.coordinator.api.update_appliance(self.puid, {self.status: str(value)})
        except LifeConnectError as api_error:
            raise ServiceValidationError(str(api_error)) from api_error
        self._attr_native_value = value
        self.async_write_ha_state()
