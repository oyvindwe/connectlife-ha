"""Provides climate entities for ConnectLife."""
import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
    PRESET_NONE
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, Platform, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    FAN_MODE,
    HVAC_MODE,
    HVAC_ACTION,
    IS_ON,
    PRESET,
    PRESETS,
    SWING_MODE,
    TARGET_HUMIDITY,
    TARGET_TEMPERATURE,
    TEMPERATURE_UNIT,
)
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries, Dictionary
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
    for appliance in coordinator.data.values():
        dictionary = Dictionaries.get_dictionary(appliance)
        if is_climate(dictionary):
            entities.append(ConnectLifeClimate(
                coordinator,
                appliance,
                dictionary,
                config_entry
            ))
    async_add_entities(entities)


def is_climate(dictionary: Dictionary):
    for prop in dictionary.properties.values():
        if hasattr(prop, Platform.CLIMATE):
            return True
    return False


class ConnectLifeClimate(ConnectLifeEntity, ClimateEntity):
    """Climate class for ConnectLife."""

    _attr_name = None
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 1
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_mode = None
    unknown_values: dict[str, int]
    target_map: dict[str, str]
    fan_mode_map: dict[int, str]
    fan_mode_reverse_map: dict[str, int]
    hvac_action_map: dict[int, HVACAction]
    hvac_mode_map: dict[int, HVACMode]
    hvac_mode_reverse_map: dict[HVACMode, int]
    preset_map: dict[str, dict[str, int]]
    swing_mode_map: dict[int, str]
    swing_mode_reverse_map: dict[str, int]
    temperature_unit_map: dict[int, UnitOfTemperature]
    min_temperature_map: dict[UnitOfTemperature: int]
    max_temperature_map: dict[UnitOfTemperature: int]

    def __init__(
            self,
            coordinator: ConnectLifeCoordinator,
            appliance: ConnectLifeAppliance,
            data_dictionary: Dictionary,
            config_entry: ConfigEntry
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance, config_entry)
        self._attr_unique_id = f"{appliance.device_id}-climate"

        self.entity_description = ClimateEntityDescription(
            key=self._attr_unique_id,
            name=appliance.device_nickname,
            translation_key=DOMAIN
        )

        self.target_map = {}
        self.fan_mode_map = {}
        self.fan_mode_reverse_map = {}
        self.hvac_action_map = {}
        self.hvac_mode_map = {}
        self.hvac_mode_reverse_map = {}
        self.preset_map = {}
        self.swing_mode_map = {}
        self.swing_mode_reverse_map = {}
        self.temperature_unit_map = {}
        self.min_temperature_map = {}
        self.max_temperature_map = {}
        self.unknown_values = {}

        for dd_entry in data_dictionary.properties.values():
            if hasattr(dd_entry, Platform.CLIMATE):
                self.target_map[dd_entry.climate.target] = dd_entry.name

        hvac_modes = []
        for target, status in self.target_map.items():
            if target == IS_ON:
                self._attr_supported_features |= ClimateEntityFeature.TURN_OFF
                self._attr_supported_features |= ClimateEntityFeature.TURN_ON
                hvac_modes.append(HVACMode.OFF)
            elif target == TARGET_HUMIDITY:
                self._attr_supported_features |= ClimateEntityFeature.TARGET_HUMIDITY
                self._attr_target_humidity = None
                self._attr_min_humidity = data_dictionary.properties[status].climate.min_value
                if min_temp := self.get_temperature_limit(self.min_temperature_map):
                    self._attr_min_temp = min_temp
                self._attr_max_humidity = data_dictionary.properties[status].climate.max_value
                if max_temp := self.get_temperature_limit(self.max_temperature_map):
                    self._attr_max_temp = max_temp
            elif target == TARGET_TEMPERATURE:
                self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
                self._attr_target_temperature = None
                self.min_temperature_map = to_temperature_map(data_dictionary.properties[status].climate.min_value)
                self.max_temperature_map = to_temperature_map(data_dictionary.properties[status].climate.max_value)
            elif target == TEMPERATURE_UNIT:
                for k, v in data_dictionary.properties[status].climate.options.items():
                    if unit := to_unit_of_temperature(v):
                        self.temperature_unit_map[k] = unit
            elif target == HVAC_MODE:
                modes = [mode.value for mode in HVACMode]
                for (k, v) in data_dictionary.properties[status].climate.options.items():
                    if v in modes:
                        mode = HVACMode(v)
                        self.hvac_mode_map[k] = mode
                        hvac_modes.append(mode)
                        self.hvac_mode_reverse_map[mode] = k
            elif target == FAN_MODE:
                self.fan_mode_map = data_dictionary.properties[status].climate.options
                self.fan_mode_reverse_map = {v: k for k, v in self.fan_mode_map.items()}
                self._attr_fan_modes = list(self.fan_mode_map.values())
                self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
                self._attr_fan_mode = None
            elif target == SWING_MODE:
                self.swing_mode_map = data_dictionary.properties[status].climate.options
                self.swing_mode_reverse_map = {v: k for k, v in self.swing_mode_map.items()}
                self._attr_swing_modes = list(self.swing_mode_map.values())
                self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
                self._attr_swing_mode = None
            elif target == HVAC_ACTION:
                actions = [action.value for action in HVACAction]
                for (k, v) in data_dictionary.properties[status].climate.options.items():
                    if v in actions:
                        self.hvac_action_map[k] = HVACAction(v)
                    else:
                        _LOGGER.warning("Not mapping %d to unknown HVACAction %s", k, v)
            self.unknown_values[status] = data_dictionary.properties[status].climate.unknown_value

        if data_dictionary.climate and PRESETS in data_dictionary.climate:
            # TODO: Check that all presets have names and convert to map in Dictionaries.
            self.preset_map = {preset.copy().pop(PRESET): preset for preset in data_dictionary.climate[PRESETS]}
            self._attr_preset_modes = list(self.preset_map.keys())
            if PRESET_NONE not in self._attr_preset_modes:
                self._attr_preset_modes.append(PRESET_NONE)
            self._attr_preset_mode = None
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE

        if HVAC_MODE not in self.target_map:
            # Assume auto
            hvac_modes.append(HVACMode.AUTO)
            if IS_ON not in self.target_map:
                self._attr_hvac_mode = HVACMode.AUTO
        self._attr_hvac_modes = hvac_modes

        self.update_state()

    @callback
    def update_state(self) -> None:
        is_on = True
        hvac_mode = HVACMode.AUTO
        for target, status in self.target_map.items():
            if status in self.coordinator.data[self.device_id].status_list:
                value = self.coordinator.data[self.device_id].status_list[status]
                if target == IS_ON:
                    # TODO: Support value mapping
                    if value == 0:
                        is_on = False
                elif target == HVAC_MODE:
                    if value in self.hvac_mode_map:
                        hvac_mode = self.hvac_mode_map[value]
                    else:
                        # Map to None without warning as we cannot add custom HVAC modes.
                        hvac_mode = None
                elif target == HVAC_ACTION:
                    if value in self.hvac_action_map:
                        self._attr_hvac_action = self.hvac_action_map[value]
                    else:
                        # Map to None without warning as we cannot add custom HVAC actions.
                        self._attr_hvac_action = None
                elif target == FAN_MODE:
                    if value in self.fan_mode_map:
                        self._attr_fan_mode = self.fan_mode_map[value]
                    else:
                        self._attr_fan_mode = None
                        _LOGGER.warning("Got unexpected value %d for %s (%s)", value, status, self.nickname)
                elif target == SWING_MODE:
                    if value in self.swing_mode_map:
                        self._attr_swing_mode = self.swing_mode_map[value]
                    else:
                        self._attr_swing_mode = None
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
                else:
                    if value == self.unknown_values[status]:
                        value = None
                    setattr(self, f"_attr_{target}", value)

        if self._attr_supported_features & ClimateEntityFeature.PRESET_MODE:
            # If current preset matches, don't change
            status_list = self.coordinator.data[self.device_id].status_list
            if (
                    self._attr_preset_mode not in self.preset_map
                    or not self.preset_map[self._attr_preset_mode].items() <= status_list.items()
            ):
                preset_mode = PRESET_NONE
                for preset, preset_map in self.preset_map.items():
                    if preset_map.items() <= status_list.items():
                        preset_mode = preset
                        break
                self._attr_preset_mode = preset_mode

        self._attr_hvac_mode = hvac_mode if is_on else HVACMode.OFF
        self._attr_available = self.coordinator.data[self.device_id].offline_state == 1

    def get_temperature_limit(self, temperature_map: [UnitOfTemperature, int]):
        if temperature_map and self._attr_temperature_unit in temperature_map:
            return temperature_map[self._attr_temperature_unit]
        else:
            return None

    async def async_set_humidity(self, humidity):
        """Set new target humidity."""
        await self.async_update_device({self.target_map[TARGET_HUMIDITY]: round(humidity)})

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE in kwargs:
            await self.async_update_device({
                self.target_map[TARGET_TEMPERATURE]: round(kwargs[ATTR_TEMPERATURE])
            })

    async def async_turn_on(self):
        """Turn the entity on."""
        # TODO: Support value mapping
        await self.async_update_device(self.add_target_temperature({self.target_map[IS_ON]: 1}))

    async def async_turn_off(self):
        """Turn the entity off."""
        # TODO: Support value mapping
        await self.async_update_device({self.target_map[IS_ON]: 0})

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        else:
            request = {}
            if self._attr_supported_features & ClimateEntityFeature.TURN_ON:
                # TODO: Support value mapping
                request[self.target_map[IS_ON]] = 1
            if HVAC_MODE in self.target_map:
                request[self.target_map[HVAC_MODE]] = self.hvac_mode_reverse_map[hvac_mode]
            await self.async_update_device(self.add_target_temperature(request))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        await self.async_update_device({
            self.target_map[FAN_MODE]: self.fan_mode_reverse_map[fan_mode]
        })

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        self._attr_preset_mode = preset_mode # Set to avoid changing to an overlapping preset
        if preset_mode in self.preset_map:
            await self.async_update_device(self.preset_map[preset_mode])

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode."""
        await self.async_update_device({
            self.target_map[SWING_MODE]: self.swing_mode_reverse_map[swing_mode]
        })

    def add_target_temperature(self, request: dict[str, int]) -> dict[str, int]:
        if TARGET_TEMPERATURE in self.target_map and self._attr_target_temperature is not None:
            request[self.target_map[TARGET_TEMPERATURE]] = round(self._attr_target_temperature)
        return request
