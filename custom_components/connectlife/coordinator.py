import async_timeout
import logging
from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Any

from connectlife.api import (
    ConnectLifeApi,
    EnergyResult,
    LifeConnectAuthError,
    LifeConnectError,
)
from connectlife.appliance import ConnectLifeAppliance
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import list_statistic_ids
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DATA_STATE_CLASS_MIGRATION_DONE, DOMAIN
from .cycle_totals import DailyCycleTotals, cycle_reading
from .dictionaries import Dictionaries
from .messages import format_retry_message
from .statistics_sources import STATISTICS_SOURCES, enabled_sensors

MAX_RETRIES = 3
STATISTICS_UPDATE_INTERVAL = timedelta(minutes=10)
STATISTICS_STORAGE_VERSION = 1
CYCLE_TOTALS_SAVE_DELAY = 5  # seconds; coalesces bursts of changes into one write

_LOGGER = logging.getLogger(__name__)


class ConnectLifeCoordinator(DataUpdateCoordinator[dict[str, ConnectLifeAppliance]]):
    """ConnectLife coordinator."""

    # We need initial data, so no retries for first request.
    error_count = MAX_RETRIES

    def __init__(self, hass, api: ConnectLifeApi):
        """Initialize coordinator."""
        self.api = api
        # Register of entities created this setup, keyed by unique ID (used by
        # cleanup_removed_entities). Instance-scoped so a reload — e.g. after
        # toggling a per-device option — starts fresh and prunes entities that
        # are no longer created, such as the offline-state binary sensor.
        self.entities: dict[str, Platform] = {}
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


class ConnectLifeStatisticsCoordinator(DataUpdateCoordinator[dict[str, EnergyResult | None]]):
    """ConnectLife statistics coordinator. Polls each appliance's statistics endpoint
    (selected per device type via the data dictionary ``statistics_source``) every 10
    minutes. Stores the fetched result per device; sensors extract their datapoint.

    Appliances whose data dictionary opts in via ``statistics.cycle_totals`` skip the cloud
    endpoint entirely: their daily totals are summed client-side from each finished cycle's
    own telemetry (see :mod:`.cycle_totals`), observed on every main-coordinator refresh,
    because the cloud endpoint re-credits completed cycles (see
    https://github.com/oyvindwe/connectlife-ha/issues/669).
    """

    def __init__(
        self,
        hass,
        api: ConnectLifeApi,
        appliance_coordinator: ConnectLifeCoordinator,
        entry_id: str,
    ):
        """Initialize statistics coordinator."""
        self.api = api
        self.appliance_coordinator = appliance_coordinator
        self.cycle_totals: dict[str, DailyCycleTotals] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass, STATISTICS_STORAGE_VERSION, f"{DOMAIN}_{entry_id}_statistics"
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_statistics",
            update_interval=STATISTICS_UPDATE_INTERVAL,
        )

    async def _async_setup(self) -> None:
        """Restore persisted cycle totals from a previous run, then take the first reading."""
        try:
            stored = await self._store.async_load()
        except Exception:
            _LOGGER.debug("Failed to load persisted statistics state", exc_info=True)
            stored = None
        if stored:
            for device_id, entry in stored.get("cycle_totals", {}).items():
                totals = DailyCycleTotals.from_dict(entry)
                if totals is not None:
                    self.cycle_totals[device_id] = totals
        self._observe_cycle_totals()

    def _state_payload(self) -> dict[str, Any]:
        """Everything worth persisting across restarts."""
        return {
            "cycle_totals": {
                device_id: totals.to_dict() for device_id, totals in self.cycle_totals.items()
            },
        }

    @callback
    def async_start_cycle_tracking(self) -> Callable[[], None]:
        """Observe every main-coordinator refresh (60s) for finished cycles.

        Returns the unsubscribe callback, to be run when the config entry unloads.
        """
        return self.appliance_coordinator.async_add_listener(self._observe_cycle_totals)

    @callback
    def _observe_cycle_totals(self) -> None:
        """Fold each opted-in appliance's current reading into its daily cycle totals."""
        today = dt_util.now().date()
        changed = False
        for device_id, appliance in self.appliance_coordinator.data.items():
            reading = cycle_reading(appliance, Dictionaries.get_dictionary(appliance))
            if reading is None:
                continue
            is_finished, energy, water = reading
            totals = self.cycle_totals.get(device_id)
            if totals is None:
                self.cycle_totals[device_id] = DailyCycleTotals.start(
                    today, is_finished, energy, water
                )
                changed = True
            else:
                was_banked = totals.banked
                if totals.observe(today, is_finished, energy, water):
                    changed = True
                    if totals.banked and not was_banked:
                        _LOGGER.debug(
                            "Banked finished cycle for %s: day total now %.2f kWh, %.2f L",
                            appliance.device_nickname,
                            totals.energy_kwh,
                            totals.water_l,
                        )
        if changed:
            self._store.async_delay_save(self._state_payload, CYCLE_TOTALS_SAVE_DELAY)
            self.async_update_listeners()

    async def _async_update_data(self) -> dict[str, EnergyResult | None]:
        """Fetch statistics for appliances whose data dictionary opts into an endpoint."""
        result: dict[str, EnergyResult | None] = {}
        for device_id, appliance in self.appliance_coordinator.data.items():
            dictionary = Dictionaries.get_dictionary(appliance)
            source = STATISTICS_SOURCES.get(dictionary.statistics_source or "")
            if source is None or not enabled_sensors(
                dictionary.statistics_source, dictionary.statistics_sensors
            ):
                continue
            if device_id in self.cycle_totals:
                # Daily totals come from the appliance's own cycle telemetry instead.
                continue
            try:
                result[device_id] = await source.fetch(self.api, appliance)
            except LifeConnectAuthError:
                # Token is rejected; stop rather than hammering the gateway (and any
                # re-login) for every remaining device. Recovers on the next cycle.
                _LOGGER.debug("Statistics auth failed; skipping remaining devices this cycle")
                break
            except Exception:
                _LOGGER.debug(
                    "Failed to fetch statistics for %s",
                    appliance.device_nickname,
                    exc_info=True,
                )
                result[device_id] = None
        return result
