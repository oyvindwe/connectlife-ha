"""Provides humidifier entities for ConnectLife."""
import logging

from homeassistant.components.humidifier import (
    HumidifierAction,
    HumidifierEntity,
    HumidifierEntityDescription,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ACTION,
    DOMAIN,
    MODE,
    IS_ON,
    TARGET_HUMIDITY,
)
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries, Dictionary
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
    for appliance in coordinator.data.values():
        dictionary = Dictionaries.get_dictionary(appliance)
        if is_humidifier(dictionary):
            entities.append(ConnectLifeHumidifier(coordinator, appliance, dictionary, config_entry))
    async_add_entities(entities)


def is_humidifier(dictionary: Dictionary):
    for prop in dictionary.properties.values():
        if hasattr(prop, Platform.HUMIDIFIER):
            return True
    return False


class ConnectLifeHumidifier(ConnectLifeEntity, HumidifierEntity):
    """Humidifier class for ConnectLife."""

    _attr_name = None
    target_map: dict[str, str]
    mode_map: dict[int, str]
    mode_reverse_map: dict[str, int]
    action_map: dict[int, HumidifierAction]

    def __init__(
            self,
            coordinator: ConnectLifeCoordinator,
            appliance: ConnectLifeAppliance,
            data_dictionary: Dictionary,
            config_entry: ConfigEntry,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, appliance, config_entry)
        self._attr_unique_id = f"{appliance.device_id}-humidifier"

        self.target_map = {}
        self.mode_map = {}
        self.mode_reverse_map = {}
        self.action_map = {}

        device_class = None
        for prop in data_dictionary.properties.values():
            if hasattr(prop, Platform.HUMIDIFIER):
                if prop.humidifier.device_class is not None:
                    device_class = prop.humidifier.device_class
                    break

        self.entity_description = HumidifierEntityDescription(
            key=self._attr_unique_id,
            name=appliance.device_nickname,
            translation_key=DOMAIN,
            device_class=device_class,
        )

        for dd_entry in data_dictionary.properties.values():
            if hasattr(dd_entry, Platform.HUMIDIFIER):
                self.target_map[dd_entry.humidifier.target] = dd_entry.name

        for target, status in self.target_map.items():
            if target == ACTION:
                actions = [action.value for action in HumidifierAction]
                for (k, v) in data_dictionary.properties[status].humidifier.options.items():
                    if v in actions:
                        self.action_map[k] = HumidifierAction(v)
                    else:
                        _LOGGER.warning("Not mapping %d to unknown HumidifierAction %s", k, v)
            elif target == MODE:
                self.mode_map = data_dictionary.properties[status].humidifier.options
                self.mode_reverse_map = {v: k for k, v in self.mode_map.items()}
                self._attr_available_modes = list(self.mode_map.values())
                self._attr_supported_features |= HumidifierEntityFeature.MODES
                self._attr_mode = None
            elif target == TARGET_HUMIDITY:
                self._attr_min_humidity = data_dictionary.properties[status].humidifier.min_value
                self._attr_max_humidity = data_dictionary.properties[status].humidifier.max_value

        self.update_state()

    @callback
    def update_state(self) -> None:
        for target, status in self.target_map.items():
            if status in self.coordinator.data[self.device_id].status_list:
                value = self.coordinator.data[self.device_id].status_list[status]
                if target == IS_ON:
                    # TODO: Support value mapping
                    self._attr_is_on = value == 1
                elif target == ACTION:
                    if value in self.action_map:
                        self._attr_action = self.action_map[value]
                    else:
                        # Map to None as we cannot add custom humidifier actions.
                        self._attr_action = None
                elif target == MODE:
                    if value in self.mode_map:
                        self._attr_mode = self.mode_map[value]
                    else:
                        self._attr_mode = None
                        _LOGGER.warning("Got unexpected value %d for %s (%s)", value, status, self.nickname)
                else:
                    setattr(self, f"_attr_{target}", value)
        self._attr_available = self.coordinator.data[self.device_id].offline_state == 1

    async def async_set_humidity(self, humidity):
        """Set new target humidity."""
        await self.async_update_device({self.target_map[TARGET_HUMIDITY]: round(humidity)})

    async def async_turn_on(self):
        """Turn the entity on."""
        if IS_ON not in self.target_map:
            _LOGGER.warning("Cannot turn on %s without is_on target.", self.nickname)
            return
        # TODO: Support value mapping
        await self.async_update_device({self.target_map[IS_ON]: 1})

    async def async_turn_off(self):
        """Turn the entity off."""
        if IS_ON not in self.target_map:
            _LOGGER.warning("Cannot turn off %s without is_on target.", self.nickname)
            return
        # TODO: Support value mapping
        await self.async_update_device({self.target_map[IS_ON]: 0})

    async def async_set_mode(self, mode):
        """Set mode."""
        await self.async_update_device({self.target_map[MODE]: self.mode_reverse_map[mode]})
