import async_timeout
import logging
from collections.abc import Mapping
from datetime import timedelta

from connectlife.api import LifeConnectAuthError, LifeConnectError, ConnectLifeApi
from connectlife.appliance import ConnectLifeAppliance
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import list_statistic_ids
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DATA_STATE_CLASS_MIGRATION_DONE, DOMAIN
from .dictionaries import Dictionaries
from .messages import format_retry_message

MAX_RETRIES = 3
ENERGY_UPDATE_INTERVAL = timedelta(minutes=10)

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
            # Note: aiohttp.ClientError is already handled by the data update
            # coordinator. TimeoutError is retried here so the UI gets the
            # same user-facing retry message as other ConnectLife API errors.
            async with async_timeout.timeout(30):
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
                _LOGGER.debug(
                    "ConnectLife API request timed out, will try %d more %s",
                    i,
                    "time" if i == 1 else "times",
                )
            else:
                raise UpdateFailed(format_retry_message(err)) from err
        except LifeConnectError as err:
            self.error_count += 1
            i = MAX_RETRIES - self.error_count
            if i > 0:
                _LOGGER.debug(
                    "ConnectLife API failed with '%s', will try %d more %s",
                    err,
                    i,
                    "time" if i == 1 else "times",
                )
            else:
                raise UpdateFailed(format_retry_message(err)) from err
        return {a.device_id: a for a in self.api.appliances}

    async def async_update_device(self, device_id: str, command: Mapping[str, int | str], properties: Mapping[str, int | str]):
        """Updates the device, and sets the properties in local copy and notify to avoid refetching."""
        await self.api.update_appliance(self.data[device_id].puid, {k: str(v) for k, v in command.items()})
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
                if entity.device_id is None:
                    continue
                device = device_reg.async_get(entity.device_id)
                if device is None:
                    continue
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
                                "device_name": device.name or "",
                            },
                        )
                    else:
                        # Self repair
                        ir.async_delete_issue(self.hass, DOMAIN, f"unavailable_device.{device_id}")

    async def find_orphaned_statistics(self) -> list[str]:
        """Return entity_ids of our sensors with stored LTS but no current ``state_class``.

        Sensors lose ``state_class`` when a property is remapped or when the
        old auto-default to ``measurement`` no longer applies. The recorder
        keeps the historical data and emits one repair per entity. Collect
        them so we can offer a single bulk-clear action.
        """
        entity_reg = er.async_get(self.hass)
        candidates: list[str] = []
        for appliance in self.data.values():
            dictionary = Dictionaries.get_dictionary(appliance)
            for name, prop in dictionary.properties.items():
                if not hasattr(prop, Platform.SENSOR):
                    continue
                if prop.sensor.state_class is not None:
                    continue
                unique_id = f"{appliance.device_id}-{name}"
                entity_id = entity_reg.async_get_entity_id(
                    Platform.SENSOR, DOMAIN, unique_id
                )
                if entity_id:
                    candidates.append(entity_id)

        if not candidates:
            return []

        recorder = get_instance(self.hass)
        metas = await recorder.async_add_executor_job(
            list_statistic_ids, self.hass, set(candidates)
        )
        return sorted(m["statistic_id"] for m in metas)

    async def update_orphaned_statistics_issue(self) -> None:
        """Create or clear the bulk repair issue for orphaned statistics.

        When no orphans are found the migration is effectively complete for
        this entry — fresh installs and lucky upgraders never had any to
        clean up. Mark the flag so we don't re-run detection on every
        future setup.
        """
        issue_id = f"orphaned_statistics.{self.config_entry.entry_id}"
        orphans = await self.find_orphaned_statistics()
        if not orphans:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    DATA_STATE_CLASS_MIGRATION_DONE: True,
                },
            )
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            data={"entry_id": self.config_entry.entry_id},
            is_fixable=True,
            severity=ir.IssueSeverity.CRITICAL,
            translation_key="orphaned_statistics",
            translation_placeholders={"count": str(len(orphans))},
        )


class ConnectLifeEnergyCoordinator(DataUpdateCoordinator[dict[str, float | None]]):
    """ConnectLife energy coordinator. Polls daily energy usage every 10 minutes."""

    def __init__(self, hass, api: ConnectLifeApi, appliance_coordinator: ConnectLifeCoordinator):
        """Initialize energy coordinator."""
        self.api = api
        self.appliance_coordinator = appliance_coordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_energy",
            update_interval=ENERGY_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, float | None]:
        """Fetch daily energy for all appliances."""
        result: dict[str, float | None] = {}
        for device_id, appliance in self.appliance_coordinator.data.items():
            try:
                result[device_id] = await self.api.get_daily_energy_kwh(
                    appliance.puid,
                    appliance.device_type_code,
                    appliance.device_feature_code,
                )
            except Exception:
                _LOGGER.debug(
                    "Failed to fetch daily energy for %s",
                    appliance.device_nickname,
                    exc_info=True,
                )
                result[device_id] = None
        return result
