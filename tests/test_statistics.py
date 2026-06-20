"""Tests for the statistics sources, coordinator fetch loop, and sensor."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from connectlife.api import LifeConnectAuthError
from homeassistant.util import dt as dt_util

from custom_components.connectlife.coordinator import ConnectLifeStatisticsCoordinator
from custom_components.connectlife.dictionaries import Dictionaries
from custom_components.connectlife.sensor import ConnectLifeStatisticsSensor
from custom_components.connectlife.statistics_sources import (
    AirDuctStatisticsSource,
    ConsumptionStatisticsSource,
    _as_float,
    _curve_today,
    enabled_sensors,
)


def _today_key() -> str:
    return dt_util.now().date().isoformat()


# -- pure helpers ----------------------------------------------------------


def test_as_float():
    assert _as_float(None) is None
    assert _as_float("1.5") == 1.5
    assert _as_float(2) == 2.0
    assert _as_float("not a number") is None


def test_curve_today_returns_value_for_today():
    curve = {_today_key(): "1.5", "2000-01-01": "9.9"}
    assert _curve_today(curve) == 1.5


def test_curve_today_missing_today_is_none():
    assert _curve_today({"2000-01-01": "9.9"}) is None


def test_curve_today_empty_or_none_is_none():
    assert _curve_today(None) is None
    assert _curve_today({}) is None


def test_curve_today_non_numeric_is_none():
    assert _curve_today({_today_key(): "n/a"}) is None


# -- enabled_sensors -------------------------------------------------------


def test_enabled_sensors_unknown_source_is_empty():
    assert enabled_sensors(None, {}) == []
    assert enabled_sensors("does_not_exist", {"daily_energy_kwh": True}) == []


def test_enabled_sensors_only_listed_true_are_created():
    assert [s.key for s in enabled_sensors("air_duct_energy", {"daily_energy_kwh": True})] == [
        "daily_energy_kwh"
    ]
    assert enabled_sensors("air_duct_energy", {"daily_energy_kwh": False}) == []
    assert enabled_sensors("air_duct_energy", {}) == []


def test_enabled_sensors_consumption_energy_and_water():
    both = enabled_sensors(
        "energy_consumption_curve",
        {"daily_energy_kwh": True, "daily_water_consumption": True},
    )
    assert [s.key for s in both] == ["daily_energy_kwh", "daily_water_consumption"]

    energy_only = enabled_sensors("energy_consumption_curve", {"daily_energy_kwh": True})
    assert [s.key for s in energy_only] == ["daily_energy_kwh"]


# -- coordinator fetch loop ------------------------------------------------


class _FakeApi:
    """Records calls; optionally raises per endpoint."""

    def __init__(self, *, air_duct=None, consumption=None, air_duct_exc=None):
        self._air_duct = air_duct
        self._consumption = consumption
        self._air_duct_exc = air_duct_exc
        self.air_duct_calls = 0
        self.consumption_calls = 0

    async def get_air_duct_energy(self, *_args):
        self.air_duct_calls += 1
        if self._air_duct_exc is not None:
            raise self._air_duct_exc
        return self._air_duct

    async def get_energy_consumption_curve(self, *_args):
        self.consumption_calls += 1
        return self._consumption


def _appliance(device_id: str, type_code: str, feature: str):
    return SimpleNamespace(
        device_id=device_id,
        device_type_code=type_code,
        device_feature_code=feature,
        puid=f"puid{device_id}",
        device_nickname=f"dev-{device_id}",
    )


def _coordinator(api, data: dict):
    # Bypass DataUpdateCoordinator.__init__ (needs hass); the fetch loop only uses
    # self.api and self.appliance_coordinator.data.
    coord = ConnectLifeStatisticsCoordinator.__new__(ConnectLifeStatisticsCoordinator)
    coord.api = api  # type: ignore[assignment]
    coord.appliance_coordinator = SimpleNamespace(data=data)  # type: ignore[assignment]
    return coord


@pytest.fixture(autouse=True)
def _clear_dictionary_cache():
    Dictionaries.dictionaries.clear()
    yield
    Dictionaries.dictionaries.clear()


async def test_coordinator_stores_results_per_device():
    api = _FakeApi(
        air_duct=SimpleNamespace(electric_total=2.0),
        consumption=SimpleNamespace(
            electric_curve={_today_key(): "1.0"}, water_curve={_today_key(): "11.0"}
        ),
    )
    data = {"ac": _appliance("ac", "009", "100"), "wm": _appliance("wm", "015", "000")}
    result = await _coordinator(api, data)._async_update_data()

    assert set(result) == {"ac", "wm"}
    assert result["ac"] is not None and result["ac"].electric_total == 2.0
    assert api.air_duct_calls == 1
    assert api.consumption_calls == 1


async def test_coordinator_auth_error_breaks_remaining_devices():
    # AC fetched first and raises auth error -> loop breaks before the washing machine.
    api = _FakeApi(air_duct_exc=LifeConnectAuthError("token rejected"))
    data = {"ac": _appliance("ac", "009", "100"), "wm": _appliance("wm", "015", "000")}
    result = await _coordinator(api, data)._async_update_data()

    assert result == {}
    assert api.air_duct_calls == 1
    assert api.consumption_calls == 0  # never reached


async def test_coordinator_generic_error_yields_none_and_continues():
    api = _FakeApi(
        air_duct_exc=ValueError("boom"),
        consumption=SimpleNamespace(
            electric_curve={_today_key(): "1.0"}, water_curve={}
        ),
    )
    data = {"ac": _appliance("ac", "009", "100"), "wm": _appliance("wm", "015", "000")}
    result = await _coordinator(api, data)._async_update_data()

    assert result["ac"] is None  # generic error -> None, not a break
    assert result["wm"] is not None and result["wm"].electric_curve  # later device still fetched
    assert api.consumption_calls == 1


async def test_coordinator_skips_device_without_statistics_source():
    api = _FakeApi()
    data = {"x": _appliance("x", "999", "000")}  # unmapped type -> no source
    result = await _coordinator(api, data)._async_update_data()

    assert result == {}
    assert api.air_duct_calls == 0
    assert api.consumption_calls == 0


# -- sensor ----------------------------------------------------------------


class _FakeStatsCoordinator:
    def __init__(self, data, last_update_success=True):
        self.data = data
        self.last_update_success = last_update_success


def _energy_sensor_def():
    return ConsumptionStatisticsSource().sensors[0]  # daily_energy_kwh


def _make_sensor(coordinator, device_id="dev1", sensor_def=None):
    appliance_coordinator = SimpleNamespace(add_entity=lambda *a, **k: None)
    appliance = SimpleNamespace(device_id=device_id)
    return ConnectLifeStatisticsSensor(
        appliance_coordinator,  # type: ignore[arg-type]
        coordinator,  # type: ignore[arg-type]
        appliance,  # type: ignore[arg-type]
        sensor_def or _energy_sensor_def(),
    )


def test_sensor_extracts_value_and_is_available():
    coord = _FakeStatsCoordinator(
        {"dev1": SimpleNamespace(electric_curve={_today_key(): "1.5"})}
    )
    sensor = _make_sensor(coord)
    assert sensor.native_value == 1.5
    assert sensor.available is True


def test_sensor_air_duct_value():
    coord = _FakeStatsCoordinator({"dev1": SimpleNamespace(electric_total=2.0)})
    sensor = _make_sensor(coord, sensor_def=AirDuctStatisticsSource().sensors[0])
    assert sensor.native_value == 2.0
    assert sensor.available is True


def test_sensor_unavailable_when_result_none():
    coord = _FakeStatsCoordinator({"dev1": None})
    sensor = _make_sensor(coord)
    assert sensor.native_value is None
    assert sensor.available is False


def test_sensor_unavailable_when_device_missing():
    coord = _FakeStatsCoordinator({})
    sensor = _make_sensor(coord)
    assert sensor.native_value is None
    assert sensor.available is False


def test_sensor_unavailable_when_last_update_failed():
    coord = _FakeStatsCoordinator(
        {"dev1": SimpleNamespace(electric_curve={_today_key(): "1.5"})},
        last_update_success=False,
    )
    sensor = _make_sensor(coord)
    assert sensor.available is False
