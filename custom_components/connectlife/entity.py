"""ConnectLife entity base class."""

import logging
import re
from abc import abstractmethod

from connectlife.api import LifeConnectError
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from connectlife.appliance import ConnectLifeAppliance

from .const import (
    CONF_DEVICES,
    CONF_DISABLE_BEEP,
    CONF_EXPOSE_OFFLINE_STATE,
    DOMAIN,
    SW_VERSION_PROPERTY,
)
from .coordinator import ConnectLifeCoordinator
from .dictionaries import Dictionaries

_LOGGER = logging.getLogger(__name__)
DISABLE_BEEP_FAILURE_THRESHOLD = 3
# The cloud rejects commands the device doesn't accept in its current state with this error.
COMMAND_REJECTED_DESCRIPTION = "Command status mutex"


def _is_command_rejected(err: LifeConnectError) -> bool:
    return COMMAND_REJECTED_DESCRIPTION in str(err)


class ConnectLifeEntity(CoordinatorEntity[ConnectLifeCoordinator]):
    """Generic ConnectLife entity (base class)."""

    _attr_has_entity_name = True
    _attr_unique_id: str
    _disable_beep = False
    _disable_beep_failure_count = 0
    _expose_offline_state = False
    _unavailable_status: str | None = None
    _unavailable_value: int | None = None

    def __init__(
            self,
            coordinator: ConnectLifeCoordinator,
            appliance: ConnectLifeAppliance,
            entity_name: str,
            platform: Platform):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.device_id = appliance.device_id
        self.nickname = appliance.device_nickname
        self._attr_unique_id = f'{appliance.device_id}-{entity_name}'
        sw_version = appliance.status_list.get(SW_VERSION_PROPERTY)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, appliance.device_id)},
            model=appliance.device_feature_name,
            hw_version=f'{appliance.device_type_code}-{appliance.device_feature_code}',
            name=appliance.device_nickname,
            suggested_area=appliance.room_name,
            sw_version=sw_version if isinstance(sw_version, str) else None,
        )
        coordinator.add_entity(self._attr_unique_id, platform)
        device = coordinator.config_entry.options.get(CONF_DEVICES, {}).get(self.device_id, {})
        self._expose_offline_state = device.get(CONF_EXPOSE_OFFLINE_STATE, False)
        self._disable_beep = device.get(CONF_DISABLE_BEEP, False)
        if self._disable_beep:
            ir.async_delete_issue(
                self.coordinator.hass,
                DOMAIN,
                f"unsupported_beep.{self.device_id}",
            )

    @property
    def available(self) -> bool:
        # CoordinatorEntity.available only checks last_update_success and
        # ignores _attr_available, so an entity is available only when all of
        # the following hold:
        #  - the coordinator's last update succeeded;
        #  - the device is still present in the coordinator data;
        #  - the device is online (offline_state == 1) — unless it is
        #    configured to expose offline_state as a binary sensor, in which
        #    case entities keep their last known value while offline instead
        #    of going unavailable;
        #  - the current value does not match the per-property `unavailable`
        #    sentinel (which marks the entity unavailable at runtime rather
        #    than skipping it at creation time).
        return (
            super().available
            and self.device_id in self.coordinator.data
            and (
                self._expose_offline_state
                or self.coordinator.data[self.device_id].offline_state == 1
            )
            and not self._is_value_unavailable()
        )

    def _is_value_unavailable(self) -> bool:
        if self._unavailable_status is None or self._unavailable_value is None:
            return False
        if self.device_id not in self.coordinator.data:
            return False
        status_list = self.coordinator.data[self.device_id].status_list
        return status_list.get(self._unavailable_status) == self._unavailable_value

    @callback
    @abstractmethod
    def update_state(self):
        """Subclasses implement this to update their state."""

    @callback
    def _refresh_state(self) -> None:
        """Run subclass update_state() unless the value matches the unavailable sentinel."""
        if not self._is_value_unavailable():
            self.update_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # A device missing from the latest poll has no values to read, so skip the
        # update. Writing the state still marks the entity unavailable.
        if self.device_id in self.coordinator.data:
            self._refresh_state()
        self.async_write_ha_state()

    async def async_update_device(
            self,
            command: dict[str, int] | dict[str, int | float],
            properties: dict[str, int] | dict[str, int | float] | None = None,
            include: list[str] | None = None,
    ):
        if properties is None:
            properties = command.copy()
        # Send along the current values of the properties the mapping includes,
        # e.g. options a program start needs. Copy, so a stored mapping keeps unchanged.
        if appliance := self.coordinator.data.get(self.device_id):
            included = Dictionaries.get_dictionary(appliance).included_values(
                command, appliance.status_list, include
            )
            if included:
                command = {**command, **included}
        try:
            if self._disable_beep:
                # Copy, so callers passing a stored mapping (e.g. a preset) keep it unchanged.
                command = {**command, "t_beep": 0}
                try:
                    await self.coordinator.async_update_device(self.device_id, command, properties)
                    self._disable_beep_failure_count = 0
                    ir.async_delete_issue(
                        self.coordinator.hass,
                        DOMAIN,
                        f"unsupported_beep.{self.device_id}",
                    )
                except LifeConnectError as err:
                    if _is_command_rejected(err):
                        # Not caused by t_beep, so don't retry or count it as a beep failure.
                        raise
                    _LOGGER.debug(
                        "Command failed with t_beep for %s (%s), retrying without",
                        self.nickname,
                        err,
                    )
                    command.pop("t_beep", None)
                    try:
                        await self.coordinator.async_update_device(self.device_id, command, properties)
                    except LifeConnectError:
                        raise err from None
                    self._disable_beep_failure_count += 1
                    if self._disable_beep_failure_count >= DISABLE_BEEP_FAILURE_THRESHOLD:
                        self._disable_beep = False
                        ir.async_create_issue(
                            self.coordinator.hass,
                            DOMAIN,
                            f"unsupported_beep.{self.device_id}",
                            is_fixable=True,
                            severity=ir.IssueSeverity.WARNING,
                            translation_key="unsupported_beep",
                            translation_placeholders={
                                "device_name": self.nickname or "",
                            },
                            data={
                                "entry_id": self.coordinator.config_entry.entry_id,
                                "device_id": self.device_id,
                            },
                        )
            else:
                await self.coordinator.async_update_device(self.device_id, command, properties)
        except LifeConnectError as api_error:
            if _is_command_rejected(api_error):
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="command_rejected"
                ) from api_error
            raise ServiceValidationError(str(api_error)) from api_error

    def to_translation_key(self, property_name: str) -> str:
        return re.sub(r'_+', '_', property_name.strip().lower().replace(" ", "_"))
