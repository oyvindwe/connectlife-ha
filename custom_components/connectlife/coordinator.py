import async_timeout
import logging
from datetime import timedelta

from connectlife.api import LifeConnectAuthError, LifeConnectError, ConnectLifeApi
from connectlife.appliance import ConnectLifeAppliance
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

MAX_RETRIES = 3

_LOGGER = logging.getLogger(__name__)


class ConnectLifeCoordinator(DataUpdateCoordinator[dict[str, ConnectLifeAppliance]]):
    """ConnectLife coordinator."""

    # We need initial data, so no retries for first request.
    error_count = MAX_RETRIES
    # Register of current entities (used for cleanup).
    entities: dict[str, Platform] = {}

    def __init__(self, hass, api: ConnectLifeApi):
        """Initialize coordinator."""
        self.api = api
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                await self.api.get_appliances()
                self.error_count = 0
        except LifeConnectAuthError as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except TimeoutError as err:
            self.error_count += 1
            i = MAX_RETRIES - self.error_count
            if i > 0:
                _LOGGER.warning(
                    "ConnectLife API request timed out, will try %d more %s",
                    i,
                    "time" if i == 1 else "times",
                )
            else:
                raise err
        except LifeConnectError as err:
            self.error_count += 1
            i = MAX_RETRIES - self.error_count
            if i > 0:
                _LOGGER.warning(
                    "ConnectLife API failed with '%s', will try %d more %s",
                    err,
                    i,
                    "time" if i == 1 else "times",
                )
            else:
                raise UpdateFailed(f"Error communicating with API: {err}")
        return {a.device_id: a for a in self.api.appliances}

    async def async_update_device(self, device_id: str, properties: dict[str, int | str]):
        """Updates the device, and sets the same data in local copy and notify to avoid refetching."""
        await self.api.update_appliance(self.data[device_id].puid, {k: str(v) for k, v in properties.items()})
        self.data[device_id].status_list.update(properties)
        self.async_update_listeners()

    def add_entity(self, entity_unique_id: str, platform: Platform):
        """Add known entity."""
        self.entities[entity_unique_id] = platform;

    async def cleanup_removed_entities(self) -> None:
        """
        Cleanup entity registry for entities converted to a different entity
        type or set to disabled in the mapping file, and create issues for
        unavailable devices.
        """

        device_reg = dr.async_get(self.hass)
        entity_reg = er.async_get(self.hass)

        for entity in er.async_entries_for_config_entry(
                entity_reg, self.config_entry.entry_id
        ):
            if entity.unique_id not in self.entities or entity.domain != self.entities[entity.unique_id]:
                device = device_reg.async_get(entity.device_id)
                for (domain, device_id) in device.identifiers:
                    if domain == DOMAIN and device_id in self.data:
                        _LOGGER.info(
                            "Entity %s (%s) is no longer mapped, removing",
                            entity.unique_id,
                            entity.domain
                        )
                        entity_reg.async_remove(entity.entity_id)

        for device in dr.async_entries_for_config_entry(device_reg, self.config_entry.entry_id):
            for (domain, device_id) in device.identifiers:
                if domain == DOMAIN:
                    if device_id not in self.data:
                        _LOGGER.warning("Unavailable device: %s", device.name)
                        ir.async_create_issue(
                            self.hass,
                            DOMAIN,
                            f"unavailable_device.{device_id}",
                            data={
                                "device_id": device.id,
                                "device_name": device.name,
                            },
                            is_fixable=True,
                            severity=ir.IssueSeverity.WARNING,
                            translation_key="unavailable_device",
                            translation_placeholders={
                                "device_name": device.name,
                            },
                        )
                    else:
                        # Self repair
                        ir.async_delete_issue(self.hass, DOMAIN, f"unavailable_device.{device_id}")
