"""Registry mapping a data dictionary ``statistics_source`` to a cloud endpoint.

Each :class:`StatisticsSource` knows how to fetch from one ConnectLife statistics
endpoint and which sensors to derive from it. Adding a new endpoint is: a new library
method, a ``StatisticsSource`` entry here, and setting ``statistics_source`` in the
relevant base data dictionaries — no coordinator/platform changes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import datetime as dt
from typing import Any

from connectlife.api import ConnectLifeApi, EnergyResult
from connectlife.appliance import ConnectLifeAppliance
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfVolume


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _curve_today(curve: dict[str, Any] | None) -> float | None:
    """Today's value from a per-day curve keyed by ISO date (e.g. the week response)."""
    if not curve:
        return None
    return _as_float(curve.get(dt.date.today().isoformat()))


@dataclass(frozen=True)
class StatisticsSensorDef:
    """One sensor derived from a statistics endpoint result.

    ``key`` is both the translation key and the unique-id suffix (and the per-sensor key
    in the data dictionary ``statistics`` block — a sensor is created only when the block
    lists ``<key>: true``). ``value`` extracts the sensor's native value from the fetched
    result (an ``EnergyResult`` subclass).
    """

    key: str
    device_class: SensorDeviceClass
    unit: str
    state_class: SensorStateClass
    value: Callable[[Any], float | None]
    icon: str | None = None


class StatisticsSource:
    """Base class: fetch one endpoint and declare its sensors."""

    key: str
    sensors: tuple[StatisticsSensorDef, ...]

    async def fetch(
        self, api: ConnectLifeApi, appliance: ConnectLifeAppliance
    ) -> EnergyResult | None:
        raise NotImplementedError


class AirDuctStatisticsSource(StatisticsSource):
    """``air_duct_energy`` (air conditioners). Today's total via ``statType=day``."""

    key = "air_duct_energy"
    sensors = (
        StatisticsSensorDef(
            "daily_energy_kwh",
            SensorDeviceClass.ENERGY,
            UnitOfEnergy.KILO_WATT_HOUR,
            SensorStateClass.TOTAL_INCREASING,
            lambda r: r.electric_total,
        ),
    )

    async def fetch(self, api, appliance):
        return await api.get_air_duct_energy(
            appliance.puid, appliance.device_type_code, appliance.device_feature_code
        )


class ConsumptionStatisticsSource(StatisticsSource):
    """``energyConsumptionCurve`` (dishwashers / washing machines).

    The endpoint has no ``statType=day``; today's values come from the week response's
    per-day ``electricCurve`` / ``waterCurve`` (``curve[today]``).
    """

    key = "energy_consumption_curve"
    sensors = (
        StatisticsSensorDef(
            "daily_energy_kwh",
            SensorDeviceClass.ENERGY,
            UnitOfEnergy.KILO_WATT_HOUR,
            SensorStateClass.TOTAL_INCREASING,
            lambda r: _curve_today(r.electric_curve),
        ),
        StatisticsSensorDef(
            "daily_water_consumption",
            SensorDeviceClass.WATER,
            UnitOfVolume.LITERS,
            SensorStateClass.TOTAL_INCREASING,
            lambda r: _curve_today(r.water_curve),
            icon="mdi:water",
        ),
    )

    async def fetch(self, api, appliance):
        return await api.get_energy_consumption_curve(
            appliance.puid, appliance.device_type_code, appliance.device_feature_code
        )


STATISTICS_SOURCES: dict[str, StatisticsSource] = {
    source.key: source
    for source in (AirDuctStatisticsSource(), ConsumptionStatisticsSource())
}


def enabled_sensors(
    statistics_source: str | None, enabled: dict[str, bool]
) -> list[StatisticsSensorDef]:
    """The sensor defs to create for a device.

    ``enabled`` are the per-sensor booleans from the data dictionary ``statistics`` block
    (key -> create?). A sensor is created only when listed ``true``; omitted or ``false``
    means not created.
    """
    source = STATISTICS_SOURCES.get(statistics_source or "")
    if source is None:
        return []
    return [s for s in source.sensors if enabled.get(s.key, False)]
