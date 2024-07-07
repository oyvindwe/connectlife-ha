"""Provides climate entities for ConnectLife."""
import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, Platform, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    FAN_MODE,
    HVAC_ACTION,
    IS_ON,
    SWING_MODE,
    TARGET_TEMPERATURE,
    TEMPERATURE_UNIT,
)
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries, Property, Climate
from .entity import ConnectLifeEntity
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
        if is_climate(dictionary):
            entities.append(ConnectLifeClimate(coordinator, appliance, dictionary))
    async_add_entities(entities)


def is_climate(dictionary: dict[str, Property]):
    for property in dictionary.values():
        if hasattr(property, Platform.CLIMATE):
            return True
    return False


class ConnectLifeClimate(ConnectLifeEntity, ClimateEntity):
    """Climate class for ConnectLife."""

    _attr_has_entity_name = True
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 1
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_mode = None
    _attr_fan_mode = None
    _attr_swing_mode = None
    target_map = {}
    fan_mode_map: dict[int, str] = {}
    fan_mode_reverse_map: dict[str, int] = {}
    hvac_action_map: dict[int, HVACMode] = {}
    swing_mode_map: dict[int, str] = {}
    swing_mode_reverse_map: dict[str, int] = {}
    temperature_unit_map: dict[int, UnitOfTemperature] = {}

    def __init__(
            self,
            coordinator: ConnectLifeCoordinator,
            appliance: ConnectLifeAppliance,
            data_dictionary: dict[str, Property]
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance)
        self._attr_unique_id = f"{appliance.device_id}-climate"

        self.entity_description = ClimateEntityDescription(
            key=self._attr_unique_id,
            name=appliance.device_nickname,
            translation_key=DOMAIN
        )

        for dd_entry in data_dictionary.values():
            if hasattr(dd_entry, Platform.CLIMATE):
                self.target_map[dd_entry.climate.target] = dd_entry.name

        hvac_modes = [HVACMode.AUTO]
        for target, status in self.target_map.items():
            if target == IS_ON:
                self._attr_supported_features |= ClimateEntityFeature.TURN_OFF
                self._attr_supported_features |= ClimateEntityFeature.TURN_ON
                hvac_modes.append(HVACMode.OFF)
            if target == TARGET_TEMPERATURE:
                self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
            if target == TEMPERATURE_UNIT:
                for k, v in data_dictionary[status].climate.options.items():
                    if v == "celsius" or v == "C":
                        self.temperature_unit_map[k] = UnitOfTemperature.CELSIUS
                    elif v == "fahrenheit" or v == "F":
                        self.temperature_unit_map[k] = UnitOfTemperature.FAHRENHEIT
            if target == FAN_MODE:
                self.fan_mode_map = data_dictionary[status].climate.options
                self.fan_mode_reverse_map = {v: k for k, v in self.fan_mode_map.items()}
                self._attr_fan_modes = list(self.fan_mode_map.values())
                self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
            if target == SWING_MODE:
                self.swing_mode_map = data_dictionary[status].climate.options
                self.swing_mode_reverse_map = {v: k for k, v in self.swing_mode_map.items()}
                self._attr_swing_modes = list(self.swing_mode_map.values())
                self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
            if target == HVAC_ACTION:
                # values = set(item.value for item in Fruit)
                actions = set(action.value for action in HVACAction)
                for (k, v) in data_dictionary[status].climate.options.items():
                    if v in actions:
                        self.hvac_action_map[k] = HVACAction(v)
                    else:
                        _LOGGER.warning("Not mapping %d to unknown HVACAction %s", k, v)

        self._attr_hvac_modes = hvac_modes
        self.update_state()

    @callback
    def update_state(self) -> None:
        for target, status in self.target_map.items():
            if status in self.coordinator.appliances[self.device_id].status_list:
                value = self.coordinator.appliances[self.device_id].status_list[status]
                if target == IS_ON:
                    # TODO: Support value mapping
                    if value == 0:
                        self._attr_hvac_mode = HVACMode.OFF
                    else:
                        # TODO: Support other modes
                        self._attr_hvac_mode = HVACMode.AUTO
                elif target == HVAC_ACTION:
                    if value in self.hvac_action_map:
                        self._attr_hvac_action = self.hvac_action_map[value]
                    else:
                        # Map to None as we canot add custom HVAC actions.
                        self._attr_hvac_action = None
                elif target == FAN_MODE:
                    if value in self.fan_mode_map:
                        self._attr_fan_mode = self.fan_mode_map[value]
                    else:
                        self._attr_fan_mode = None
                        _LOGGER.warning("Got unexpected value %d for %s", value, status)
                elif target == SWING_MODE:
                    if value in self.swing_mode_map:
                        self._attr_swing_mode = self.swing_mode_map[value]
                    else:
                        self._attr_swing_mode = None
                        _LOGGER.warning("Got unexpected value %d for %s", value, status)
                elif target == TEMPERATURE_UNIT:
                    if value in self.temperature_unit_map:
                        self._attr_temperature_unit = self.temperature_unit_map[value]
                    else:
                        _LOGGER.warning("Got unexpected value %d for %s", value, status)
                else:
                    setattr(self, f"_attr_{target}", value)
        self._attr_available = self.coordinator.appliances[self.device_id]._offline_state == 1

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE in kwargs and TARGET_TEMPERATURE in self.target_map:
            target_temperature = round(kwargs[ATTR_TEMPERATURE])
            await self.coordinator.api.update_appliance(self.puid, {self.target_map[TARGET_TEMPERATURE]: target_temperature})
            self._attr_target_temperature = target_temperature
            self.async_write_ha_state()

    async def async_turn_on(self):
        """Turn the entity on."""
        # TODO: Support value mapping
        await self.coordinator.api.update_appliance(self.puid, {self.target_map[IS_ON]: 1})
        self.hvac_mode = HVACMode.AUTO
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn the entity off."""
        # TODO: Support value mapping
        await self.coordinator.api.update_appliance(self.puid, {self.target_map[IS_ON]: 0})
        self.hvac_mode = HVACMode.OFF
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        elif hvac_mode == HVACMode.AUTO:
            await self.async_turn_on()
        # self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        await  self.coordinator.api.update_appliance(self.puid, {
            self.target_map[FAN_MODE]: self.fan_mode_reverse_map[fan_mode]
        })
        self._attr_fan_mode = fan_mode
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode."""
        await self.coordinator.api.update_appliance(self.puid, {
            self.target_map[SWING_MODE]: self.swing_mode_reverse_map[swing_mode]
        })
        self._attr_swing_mode = swing_mode
        self.async_write_ha_state()
