"""Tests for the one-time cooling/heating output unit migration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_metadata,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.connectlife.const import DOMAIN
from custom_components.connectlife.migrations import async_migrate_qvalue_units


def _register(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    unique_id: str,
    unit: str | None = "BTU/h",
    options: dict | None = None,
) -> er.RegistryEntry:
    registry = er.async_get(hass)
    registry_entry = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        unique_id,
        config_entry=entry,
        unit_of_measurement=unit,
    )
    for domain, domain_options in (options or {}).items():
        registry_entry = registry.async_update_entity_options(
            registry_entry.entity_id, domain, domain_options
        )
    return registry_entry


def _private(hass: HomeAssistant, entity_id: str) -> dict | None:
    registry_entry = er.async_get(hass).async_get(entity_id)
    assert registry_entry
    return registry_entry.options.get("sensor.private")


async def test_suggested_unit_btu_becomes_w(hass: HomeAssistant) -> None:
    """On 1.1.0, Home Assistant stored BTU/h as the suggested unit: switch it to W."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    cool = _register(
        hass, entry, "dev-f_cool_qvalue", unit="BTU/h",
        options={"sensor.private": {"suggested_unit_of_measurement": "BTU/h", "other": 1}},
    )

    await async_migrate_qvalue_units(hass, entry)

    assert _private(hass, cool.entity_id) == {"suggested_unit_of_measurement": "W", "other": 1}


async def test_upgrade_from_before_1_1_0_sets_w(hass: HomeAssistant) -> None:
    """Before 1.1.0 there's no suggested unit yet: set W, so Home Assistant doesn't store BTU/h."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    heat = _register(hass, entry, "dev-f_heat_qvalue", unit="BTU/h")

    await async_migrate_qvalue_units(hass, entry)

    assert _private(hass, heat.entity_id) == {"suggested_unit_of_measurement": "W"}


async def test_leaves_other_cases_alone(hass: HomeAssistant) -> None:
    """User-picked units, W entities and other sensors are untouched."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    user_unit = _register(
        hass, entry, "dev1-f_cool_qvalue",
        options={
            "sensor": {"unit_of_measurement": "kW"},
            "sensor.private": {"suggested_unit_of_measurement": "BTU/h"},
        },
    )
    already_w = _register(hass, entry, "dev2-f_cool_qvalue", unit="W")
    other = _register(hass, entry, "dev1-f_other", unit="BTU/h")

    await async_migrate_qvalue_units(hass, entry)

    assert _private(hass, user_unit.entity_id) == {"suggested_unit_of_measurement": "BTU/h"}
    assert _private(hass, already_w.entity_id) is None
    assert _private(hass, other.entity_id) is None


async def _import_statistics(hass: HomeAssistant, statistic_id: str, unit: str, mean: float) -> None:
    start = dt_util.start_of_local_day() - timedelta(days=1)
    async_import_statistics(
        hass,
        {
            "mean_type": StatisticMeanType.ARITHMETIC,
            "has_sum": False,
            "name": None,
            "source": "recorder",
            "statistic_id": statistic_id,
            "unit_class": "power",
            "unit_of_measurement": unit,
        },
        [{"start": start, "mean": mean, "min": mean, "max": mean}],
    )
    await async_wait_recording_done(hass)


async def test_statistics_relabelled_without_converting(
    recorder_mock: Recorder, hass: HomeAssistant
) -> None:
    """Old statistics stored as BTU/h hold W values: relabel them to W, keep the values."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    cool = _register(hass, entry, "dev-f_cool_qvalue", unit="BTU/h")
    heat = _register(hass, entry, "dev-f_heat_qvalue", unit="W")
    await _import_statistics(hass, cool.entity_id, "BTU/h", 1200)
    await _import_statistics(hass, heat.entity_id, "W", 800)

    await async_migrate_qvalue_units(hass, entry)
    await async_wait_recording_done(hass)

    metadata = await recorder_mock.async_add_executor_job(
        lambda: get_metadata(hass, statistic_ids={cool.entity_id, heat.entity_id})
    )
    assert metadata[cool.entity_id][1]["unit_of_measurement"] == "W"
    assert metadata[heat.entity_id][1]["unit_of_measurement"] == "W"
    stats = await recorder_mock.async_add_executor_job(
        lambda: statistics_during_period(
            hass,
            dt_util.start_of_local_day() - timedelta(days=2),
            None,
            {cool.entity_id},
            "hour",
            None,
            {"mean"},
        )
    )
    assert stats[cool.entity_id][0].get("mean") == 1200
