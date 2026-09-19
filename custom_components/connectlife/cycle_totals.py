"""Daily energy/water totals summed from an appliance's own per-cycle telemetry.

The ConnectLife cloud statistics endpoint is unreliable for some appliances: it credits
completed cycles again on an hourly cadence and can report totals for days with no cycles
(see https://github.com/oyvindwe/connectlife-ha/issues/669). The appliance's own
per-cycle counters (e.g. ``Electricit_consumption``/``Water_consumption``) match the
on-device display, so for devices that opt in via the data dictionary's
``statistics.cycle_totals`` block each finished cycle is banked once into a day total.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from connectlife.appliance import ConnectLifeAppliance

from .dictionaries import Dictionary, Property

_DECIMALS = 2


def read_number(
    name: str, prop: Property, status_list: Mapping[str, Any]
) -> float | None:
    """A numeric property's value, mirroring ``ConnectLifeStatusSensor.update_state``:
    ``combine`` sources are summed (skipping their ``unknown_value``), then the sensor
    ``unknown_value`` and ``multiplier`` apply. None if the appliance doesn't report it.
    """
    sensor = getattr(prop, "sensor", None)
    unknown_value = sensor.unknown_value if sensor is not None else None
    multiplier = sensor.multiplier if sensor is not None else None

    combined: float | None = None
    if prop.combine:
        total = 0.0
        has_sources = False
        for source in prop.combine:
            src_value = status_list.get(source["property"])
            if isinstance(src_value, (int, float)) and not isinstance(src_value, bool):
                if "unknown_value" in source and src_value == source["unknown_value"]:
                    continue
                total += src_value * source.get("multiplier", 1)
                has_sources = True
        if has_sources:
            combined = total

    if combined is not None:
        value = combined
    else:
        raw = status_list.get(name)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            return None
        value = float(raw)
    if value == unknown_value:
        return None
    if multiplier is not None:
        value *= multiplier
    return value


@dataclass
class DailyCycleTotals:
    """Running energy/water totals for one appliance's current local day.

    ``banked`` is True while the appliance sits in its ``finished`` phase after that
    cycle has been added, so a finished state that persists for hours is counted once.
    ``prev_energy``/``prev_water`` are the previous non-finished reading (not persisted);
    the larger of that and the reading at ``finished`` is banked, in case the appliance
    zeroes its counters the moment the cycle ends.
    """

    day: date
    energy_kwh: float = 0.0
    water_l: float = 0.0
    banked: bool = False
    prev_energy: float | None = None
    prev_water: float | None = None

    @classmethod
    def start(
        cls, today: date, is_finished: bool, energy: float, water: float
    ) -> DailyCycleTotals:
        """First sight of an appliance. An already-finished cycle is treated as counted:
        we can't tell when it finished, and undercounting beats double counting."""
        if is_finished:
            return cls(today, banked=True)
        return cls(today, prev_energy=energy, prev_water=water)

    def observe(self, today: date, is_finished: bool, energy: float, water: float) -> bool:
        """Fold in one reading; returns whether persisted state changed."""
        changed = False
        if self.day != today:
            self.day = today
            self.energy_kwh = 0.0
            self.water_l = 0.0
            changed = True

        if is_finished:
            if not self.banked:
                self.energy_kwh = round(
                    self.energy_kwh + max(energy, self.prev_energy or 0.0), _DECIMALS
                )
                self.water_l = round(
                    self.water_l + max(water, self.prev_water or 0.0), _DECIMALS
                )
                self.banked = True
                changed = True
        else:
            if self.banked:
                self.banked = False
                changed = True
            self.prev_energy = energy
            self.prev_water = water
        return changed

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "energy_kwh": self.energy_kwh,
            "water_l": self.water_l,
            "banked": self.banked,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DailyCycleTotals | None:
        try:
            return cls(
                day=date.fromisoformat(data["day"]),
                energy_kwh=float(data["energy_kwh"]),
                water_l=float(data["water_l"]),
                banked=bool(data["banked"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


def cycle_reading(
    appliance: ConnectLifeAppliance, dictionary: Dictionary
) -> tuple[bool, float, float] | None:
    """``(is_finished, energy_kwh, water_l)`` for an appliance opted in to cycle totals,
    or None if it isn't (or doesn't currently report all the configured properties)."""
    config = dictionary.cycle_totals
    if config is None:
        return None
    status_list = appliance.status_list
    phase = status_list.get(config.phase)
    energy_prop = dictionary.properties.get(config.energy)
    water_prop = dictionary.properties.get(config.water)
    if phase is None or energy_prop is None or water_prop is None:
        return None
    energy = read_number(config.energy, energy_prop, status_list)
    water = read_number(config.water, water_prop, status_list)
    if energy is None or water is None:
        return None
    return phase == config.finished, energy, water
