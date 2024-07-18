"""ConnectLife entity base class."""

from abc import abstractmethod

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from connectlife.appliance import ConnectLifeAppliance

from .const import (
    CONF_DEVICES,
    CONF_DISABLE_BEEP,
    DOMAIN,
)
from .coordinator import ConnectLifeCoordinator


class ConnectLifeEntity(CoordinatorEntity[ConnectLifeCoordinator]):
    """Generic ConnectLife entity (base class)."""

    _attr_has_entity_name = True
    _disable_beep = False

    def __init__(
            self,
            coordinator: ConnectLifeCoordinator,
            appliance: ConnectLifeAppliance,
            config_entry: ConfigEntry = None):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.device_id = appliance.device_id
        self.nickname = appliance.device_nickname
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, appliance.device_id)},
            model=appliance.device_feature_name,
            hw_version=f'{appliance.device_type_code}-{appliance.device_feature_code}',
            name=appliance.device_nickname,
            suggested_area=appliance.room_name,
        )
        if config_entry and CONF_DEVICES in config_entry.options:
            devices = config_entry.options[CONF_DEVICES]
            if self.device_id in devices:
                device = devices[self.device_id]
                if CONF_DISABLE_BEEP in device:
                    self._disable_beep = device[CONF_DISABLE_BEEP]

    @callback
    @abstractmethod
    def update_state(self):
        """Subclasses implement this to update their state."""

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update_state()
        self.async_write_ha_state()

    async def async_update_device(self, properties: dict[str, int | str]):
        if self._disable_beep:
            properties["t_beep"] = 0
        await self.coordinator.async_update_device(self.device_id, properties)
