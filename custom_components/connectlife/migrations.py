"""One-time fixes to entity registry and recorder data left by earlier versions."""

from __future__ import annotations

import functools
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_UNIT_OF_MEASUREMENT, Platform, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

# Air conditioner cooling/heating output: shown in BTU/h before 1.1.0, but the values were always W (#877, #899).
QVALUE_PROPERTIES = ("f_cool_qvalue", "f_heat_qvalue")
_SENSOR_PRIVATE = f"{Platform.SENSOR}.private"
_SUGGESTED_UNIT = "suggested_unit_of_measurement"


async def async_migrate_qvalue_units(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Show the cooling/heating output in W and relabel its old statistics from BTU/h to W.

    When an entity's unit changes to one Home Assistant can convert to, it stores the old unit as the entity's
    suggested unit, so the sensor kept showing BTU/h after 1.1.0, and its long-term statistics stay in BTU/h. The old
    statistics hold the device's values, which are W, so relabelling them without converting corrects them. Must run
    before the sensor platform is set up. Safe to run on every setup: it only acts on BTU/h.
    """
    registry = er.async_get(hass)
    statistic_ids: set[str] = set()
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.domain != Platform.SENSOR or not registry_entry.unique_id.endswith(
            tuple(f"-{name}" for name in QVALUE_PROPERTIES)
        ):
            continue
        statistic_ids.add(registry_entry.entity_id)
        if CONF_UNIT_OF_MEASUREMENT in registry_entry.options.get(Platform.SENSOR, {}):
            continue  # The user picked a display unit.
        private = registry_entry.options.get(_SENSOR_PRIVATE)
        if private is None:
            # Upgrading from before 1.1.0: Home Assistant would store BTU/h as the suggested unit.
            needs_update = registry_entry.unit_of_measurement == UnitOfPower.BTU_PER_HOUR
        else:
            needs_update = private.get(_SUGGESTED_UNIT) == UnitOfPower.BTU_PER_HOUR
        if needs_update:
            _LOGGER.info("Showing %s in W instead of BTU/h", registry_entry.entity_id)
            registry.async_update_entity_options(
                registry_entry.entity_id,
                _SENSOR_PRIVATE,
                {**(private or {}), _SUGGESTED_UNIT: UnitOfPower.WATT},
            )

    if statistic_ids and "recorder" in hass.config.components:
        await _async_relabel_statistics(hass, statistic_ids)


async def _async_relabel_statistics(hass: HomeAssistant, statistic_ids: set[str]) -> None:
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import (
        async_update_statistics_metadata,
        get_metadata,
    )

    metadata = await get_instance(hass).async_add_executor_job(
        functools.partial(get_metadata, hass, statistic_ids=statistic_ids)
    )
    for statistic_id, (_, meta) in metadata.items():
        if meta["unit_of_measurement"] != UnitOfPower.BTU_PER_HOUR:
            continue
        _LOGGER.info("Relabelling the long-term statistics of %s from BTU/h to W", statistic_id)
        async_update_statistics_metadata(
            hass,
            statistic_id,
            new_unit_class="power",
            new_unit_of_measurement=UnitOfPower.WATT,
        )
