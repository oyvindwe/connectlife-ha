"""ConnectLife entity base class."""

from .const import (
    DOMAIN,
)
from .coordinator import ConnectLifeCoordinator
from connectlife.appliance import ConnectLifeAppliance
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity


class ConnectLifeEntity(CoordinatorEntity[ConnectLifeCoordinator]):
    """Generic ConnectLife entity (base class)."""

    def __init__(self, coordinator: ConnectLifeCoordinator, appliance: ConnectLifeAppliance):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.device_id = appliance.device_id
        self.puid = appliance.puid
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, appliance.device_id)},
            model=appliance.device_feature_name,
            name=appliance.device_nickname,
            suggested_area=appliance.room_name,
        )
