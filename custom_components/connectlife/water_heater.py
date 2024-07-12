"""Provides water heater entities for ConnectLife."""
import logging

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityEntityDescription,
    WaterHeaterEntityFeature,
    STATE_OFF
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, Platform, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CURRENT_OPERATION,
    DOMAIN,
    IS_AWAY_MODE_ON,
    STATE,
    TARGET_TEMPERATURE,
    TEMPERATURE_UNIT,
)
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries, Property
from .entity import ConnectLifeEntity
from .temperature import to_temperature_map, to_unit_of_temperature
from connectlife.appliance import ConnectLifeAppliance

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ConnectLife sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    for appliance in coordinator.appliances.values():
        dictionary = Dictionaries.get_dictionary(appliance)
        if is_water_heater(dictionary):
            entities.append(ConnectLifeWaterHeater(coordinator, appliance, dictionary))
    async_add_entities(entities)


def is_water_heater(dictionary: dict[str, Property]):
    for prop in dictionary.values():
        if hasattr(prop, Platform.WATER_HEATER):
            return True
    return False


class ConnectLifeWaterHeater(ConnectLifeEntity, WaterHeaterEntity):
    """WaterHeater class for ConnectLife."""

    _attr_name = None
    _attr_precision = PRECISION_WHOLE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    unknown_values: dict[str, int]
    target_map: dict[str, str]
    operation_map: dict[int, str]
    operation_reverse_map: dict[str, int]
    state_map: dict[int, str]
    state_reverse_map: dict[str, int]
    away_mode_on: int
    away_mode_off: int
    state_on: str
    temperature_unit_map: dict[int, UnitOfTemperature]
    min_temperature_map: dict[UnitOfTemperature: int]
    max_temperature_map: dict[UnitOfTemperature: int]

    def __init__(
            self,
            coordinator: ConnectLifeCoordinator,
            appliance: ConnectLifeAppliance,
            data_dictionary: dict[str, Property]
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance)
        self._attr_unique_id = f"{appliance.device_id}-waterheater"

        self.entity_description = WaterHeaterEntityEntityDescription(
            key=self._attr_unique_id,
            name=appliance.device_nickname,
            translation_key=DOMAIN
        )

        self.target_map = {}
        self.operation_map = {}
        self.operation_reverse_map = {}
        self.state_map = {}
        self.state_reverse_map = {}
        self.temperature_unit_map = {}
        self.min_temperature_map = {}
        self.max_temperature_map = {}
        self.unknown_values = {}

        for dd_entry in data_dictionary.values():
            if hasattr(dd_entry, Platform.WATER_HEATER):
                self.target_map[dd_entry.water_heater.target] = dd_entry.name

        for target, status in self.target_map.items():
            if target == TARGET_TEMPERATURE:
                self._attr_supported_features |= WaterHeaterEntityFeature.TARGET_TEMPERATURE
                self._attr_target_temperature = None
                self.min_temperature_map = to_temperature_map(data_dictionary[status].water_heater.min_value)
                self.max_temperature_map = to_temperature_map(data_dictionary[status].water_heater.max_value)
            elif target == TEMPERATURE_UNIT:
                for k, v in data_dictionary[status].water_heater.options.items():
                    if unit := to_unit_of_temperature(v):
                        self.temperature_unit_map[k] = unit
            elif target == STATE:
                # TODO: map to multiple states
                self._attr_supported_features |= WaterHeaterEntityFeature.ON_OFF
                self.state_map = data_dictionary[status].water_heater.options
                self.state_reverse_map = {v: k for k, v in self.state_map.items()}
                self.state_on = filter(lambda v: v != STATE_OFF, self.state_map.values())
                self._attr_states = list(self.state_map.values())
                self._attr_state = None
            elif target == CURRENT_OPERATION:
                self.operation_map = data_dictionary[status].water_heater.options
                self.operation_reverse_map = {v: k for k, v in self.operation_map.items()}
                self._attr_operation_list = list(self.operation_map.values())
                self._attr_supported_features |= WaterHeaterEntityFeature.OPERATION_MODE
                self._attr_current_operation = None
            elif target == IS_AWAY_MODE_ON:
                self._attr_supported_features |= WaterHeaterEntityFeature.AWAY_MODE
                reverse = {v: k for k, v in data_dictionary[status].water_heater.options.items()}
                self.away_mode_on = reverse[True]
                self.away_mode_off = reverse[False]
            self.unknown_values[status] = data_dictionary[status].water_heater.unknown_value

        if TEMPERATURE_UNIT not in self.target_map:
            if min_temp := self.get_temperature_limit(self.min_temperature_map):
                self._attr_min_temp = min_temp
            if max_temp := self.get_temperature_limit(self.max_temperature_map):
                self._attr_max_temp = max_temp

        self.update_state()

    @callback
    def update_state(self) -> None:
        for target, status in self.target_map.items():
            if status in self.coordinator.appliances[self.device_id].status_list:
                value = self.coordinator.appliances[self.device_id].status_list[status]
                if target == STATE:
                    if value in self.state_map:
                        self._attr_state = self.state_map[value]
                    else:
                        self._attr_state = None
                        _LOGGER.warning("Got unexpected value %d for %s (%s)", value, status, self.nickname)
                elif target == CURRENT_OPERATION:
                    if value in self.operation_map:
                        self._attr_current_operation = self.operation_map[value]
                    else:
                        self._attr_current_operation = None
                        _LOGGER.warning("Got unexpected value %d for %s (%s)", value, status, self.nickname)
                elif target == TEMPERATURE_UNIT:
                    if value in self.temperature_unit_map:
                        self._attr_temperature_unit = self.temperature_unit_map[value]
                        if min_temp := self.get_temperature_limit(self.min_temperature_map):
                            self._attr_min_temp = min_temp
                        if max_temp := self.get_temperature_limit(self.max_temperature_map):
                            self._attr_max_temp = max_temp
                    else:
                        _LOGGER.warning("Got unexpected value %d for %s (%s)", value, status, self.nickname)
                elif target == IS_AWAY_MODE_ON:
                    self._attr_is_away_mode_on = IS_AWAY_MODE_ON == self.is_away_mode_on
                else:
                    if value == self.unknown_values[status]:
                        value = None
                    setattr(self, f"_attr_{target}", value)

        self._attr_available = self.coordinator.appliances[self.device_id].offline_state == 1

    def get_temperature_limit(self, temperature_map: [UnitOfTemperature, int]):
        if temperature_map and self._attr_temperature_unit in temperature_map:
            return temperature_map[self._attr_temperature_unit]
        else:
            return None

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE in kwargs and TARGET_TEMPERATURE in self.target_map:
            target_temperature = round(kwargs[ATTR_TEMPERATURE])
            await self.coordinator.api.update_appliance(
                self.puid,
                {
                    self.target_map[TARGET_TEMPERATURE]:
                        target_temperature
                }
            )
            self._attr_target_temperature = target_temperature
            self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.coordinator.api.update_appliance(
            self.puid,
            {
                self.target_map[STATE]: self.reverse_state_map[self.state_on]
            }
        )
        self._attr_state = self.state_on
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.coordinator.api.update_appliance(
            self.puid,
            {
                self.target_map[STATE]: self.state_reverse_map[STATE_OFF]
            }
        )
        self._attr_state = STATE_OFF
        self.async_write_ha_state()

    async def async_turn_away_mode_on(self) -> None:
        """Turn on away mode."""
        await self.coordinator.api.update_appliance(
            self.puid,
            {
                self.target_map[IS_AWAY_MODE_ON]: self.away_mode_on
            }
        )
        self._attr_is_away_mode_on = True
        self.async_write_ha_state()

    async def async_turn_away_mode_off(self) -> None:
        """Turn on away mode."""
        await self.coordinator.api.update_appliance(
            self.puid,
            {
                self.target_map[IS_AWAY_MODE_ON]: self.away_mode_off
            }
        )
        self._attr_is_away_mode_on = False
        self.async_write_ha_state()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set the operation mode."""
        await self.coordinator.api.update_appliance(self.puid, {
            self.target_map[CURRENT_OPERATION]: self.operation_reverse_map[operation_mode]
        })
        self._attr_current_operation = operation_mode
        self.async_write_ha_state()
