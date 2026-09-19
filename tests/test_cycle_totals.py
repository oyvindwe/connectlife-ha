"""Tests for deriving the daily energy/water totals from finished cycles' own telemetry.

The cloud statistics endpoint credits completed cycles again hourly and reports energy for
days with no cycles (#669), so opted-in appliances sum each finished cycle's own counters.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

import pytest
from connectlife.appliance import ConnectLifeAppliance
from homeassistant.util import dt as dt_util

from custom_components.connectlife.coordinator import ConnectLifeStatisticsCoordinator
from custom_components.connectlife.cycle_totals import (
    DailyCycleTotals,
    cycle_reading,
    read_number,
)
from custom_components.connectlife.dictionaries import (
    CycleTotalsConfig,
    Dictionaries,
    Dictionary,
    Property,
)
from custom_components.connectlife.sensor import ConnectLifeStatisticsSensor
from custom_components.connectlife.statistics_sources import (
    AirDuctStatisticsSource,
    ConsumptionStatisticsSource,
)

FINISHED = 10
RUNNING = 3
IDLE = 0

DAY1 = date(2026, 9, 17)
DAY2 = date(2026, 9, 18)


def _today_key() -> str:
    return dt_util.now().date().isoformat()


# -- read_number -------------------------------------------------------------


def _combined(name: str) -> Property:
    """A counter reported as ``<name>_int`` + ``<name>_dec`` * 0.01 (like Electricit_consumption)."""
    return Property(
        {
            "property": name,
            "combine": [{"property": f"{name}_int"}, {"property": f"{name}_dec", "multiplier": 0.01}],
        }
    )


def test_read_number_sums_combined_sources_with_multiplier():
    status = {"Energy_int": 1, "Energy_dec": 4}
    assert read_number("Energy", _combined("Energy"), status) == pytest.approx(1.04)


def test_read_number_combined_skips_source_unknown_value():
    prop = Property(
        {
            "property": "P",
            "combine": [{"property": "A", "unknown_value": 65535}, {"property": "B"}],
        }
    )
    assert read_number("P", prop, {"A": 65535, "B": 7}) == 7.0


def test_read_number_plain_property_applies_sensor_multiplier():
    prop = Property({"property": "P", "sensor": {"multiplier": 0.1}})
    assert read_number("P", prop, {"P": 50}) == pytest.approx(5.0)


def test_read_number_sensor_unknown_value_is_none():
    prop = Property({"property": "P", "sensor": {"unknown_value": -1}})
    assert read_number("P", prop, {"P": -1}) is None


def test_read_number_missing_or_non_numeric_is_none():
    assert read_number("Energy", _combined("Energy"), {}) is None
    assert read_number("P", Property({"property": "P"}), {"P": "on"}) is None
    assert read_number("P", Property({"property": "P"}), {}) is None


# -- DailyCycleTotals --------------------------------------------------------


def test_finished_cycle_is_banked_once_however_long_finished_persists():
    totals = DailyCycleTotals.start(DAY1, False, 0.0, 0.0)

    assert totals.observe(DAY1, False, 0.5, 20.0) is False  # running: nothing to persist
    assert totals.observe(DAY1, True, 1.04, 43.2) is True
    assert (totals.energy_kwh, totals.water_l) == (1.04, 43.2)

    # The appliance can sit in `finished` for hours; the cycle must not be counted again.
    for _ in range(100):
        assert totals.observe(DAY1, True, 1.04, 43.2) is False
    assert (totals.energy_kwh, totals.water_l) == (1.04, 43.2)


def test_each_new_cycle_adds_to_the_day_total():
    totals = DailyCycleTotals.start(DAY1, False, 0.0, 0.0)
    totals.observe(DAY1, True, 1.04, 43.2)

    assert totals.observe(DAY1, False, 0.0, 0.0) is True  # leaving finished re-arms banking
    totals.observe(DAY1, False, 0.1, 2.0)
    totals.observe(DAY1, True, 0.18, 5.5)

    assert totals.energy_kwh == 1.22
    assert totals.water_l == 48.7


def test_banks_last_running_reading_if_counters_zero_at_finish():
    totals = DailyCycleTotals.start(DAY1, False, 0.0, 0.0)
    totals.observe(DAY1, False, 1.04, 43.2)

    totals.observe(DAY1, True, 0.0, 0.0)  # appliance zeroed its counters as the cycle ended

    assert (totals.energy_kwh, totals.water_l) == (1.04, 43.2)


def test_day_rollover_resets_totals_but_not_an_already_banked_finished_state():
    totals = DailyCycleTotals.start(DAY1, False, 0.0, 0.0)
    totals.observe(DAY1, True, 1.04, 43.2)

    changed = totals.observe(DAY2, True, 1.04, 43.2)  # still sitting in `finished` after midnight

    assert changed is True
    assert totals.day == DAY2
    assert (totals.energy_kwh, totals.water_l) == (0.0, 0.0)  # not re-banked into the new day


def test_cycle_finishing_after_midnight_is_credited_to_the_new_day():
    totals = DailyCycleTotals.start(DAY1, False, 0.0, 0.0)
    totals.observe(DAY1, False, 0.9, 30.0)  # cycle running late in the evening

    totals.observe(DAY2, True, 1.04, 43.2)  # ...finishes after midnight

    assert totals.day == DAY2
    assert (totals.energy_kwh, totals.water_l) == (1.04, 43.2)


def test_first_sight_of_an_already_finished_cycle_is_not_counted():
    totals = DailyCycleTotals.start(DAY1, True, 1.04, 43.2)

    assert (totals.energy_kwh, totals.water_l) == (0.0, 0.0)
    assert totals.observe(DAY1, True, 1.04, 43.2) is False  # and stays counted-as-done


def test_totals_round_trip_through_storage_format():
    totals = DailyCycleTotals(DAY1, energy_kwh=1.22, water_l=48.7, banked=True)

    restored = DailyCycleTotals.from_dict(totals.to_dict())

    assert restored == totals


def test_malformed_stored_totals_are_discarded():
    assert DailyCycleTotals.from_dict({}) is None
    assert DailyCycleTotals.from_dict({"day": "nope", "energy_kwh": 1, "water_l": 1, "banked": True}) is None
    assert DailyCycleTotals.from_dict({"day": "2026-09-17", "energy_kwh": "x", "water_l": 1, "banked": True}) is None


# -- data dictionary parsing -------------------------------------------------

_CYCLE_TOTALS_YAML = {
    "phase": "Current_program_phase",
    "finished": 10,
    "energy": "Electricit_consumption",
    "water": "Water_consumption",
}


def test_dictionary_parses_cycle_totals_and_keeps_it_out_of_the_sensor_flags(build_dictionary):
    dictionary = build_dictionary(
        sub={
            "statistics": {
                "source": "energy_consumption_curve",
                "daily_energy_kwh": True,
                "daily_water_consumption": True,
                "cycle_totals": _CYCLE_TOTALS_YAML,
            }
        },
    )

    assert dictionary.cycle_totals == CycleTotalsConfig(
        phase="Current_program_phase",
        finished=10,
        energy="Electricit_consumption",
        water="Water_consumption",
    )
    assert dictionary.statistics_source == "energy_consumption_curve"
    assert dictionary.statistics_sensors == {
        "daily_energy_kwh": True,
        "daily_water_consumption": True,
    }


def test_dictionary_without_cycle_totals_has_none(build_dictionary):
    dictionary = build_dictionary(
        base={"statistics": {"source": "energy_consumption_curve", "daily_energy_kwh": True}}
    )

    assert dictionary.cycle_totals is None


def test_base_cycle_totals_is_replaced_by_a_feature_statistics_block(build_dictionary):
    # Same rule as the rest of `statistics`: a feature block replaces the base's entirely,
    # so a variant that drops cycle_totals goes back to the cloud endpoint.
    dictionary = build_dictionary(
        base={
            "statistics": {
                "source": "energy_consumption_curve",
                "daily_energy_kwh": True,
                "cycle_totals": _CYCLE_TOTALS_YAML,
            }
        },
        sub={"statistics": {"source": "energy_consumption_curve", "daily_energy_kwh": True}},
    )

    assert dictionary.cycle_totals is None


# -- cycle_reading -----------------------------------------------------------

_CFG = CycleTotalsConfig(phase="Phase", finished=FINISHED, energy="Energy", water="Water")


def _cycle_dictionary(cycle_totals: CycleTotalsConfig | None = _CFG) -> Dictionary:
    return Dictionary(
        climate=None,
        properties={
            "Phase": Property({"property": "Phase"}),
            "Energy": _combined("Energy"),
            "Water": _combined("Water"),
        },
        buttons=[],
        statistics_source="energy_consumption_curve",
        statistics_sensors={"daily_energy_kwh": True, "daily_water_consumption": True},
        cycle_totals=cycle_totals,
    )


def _status(phase=IDLE, energy=(0, 0), water=(0, 0)) -> dict:
    return {
        "Phase": phase,
        "Energy_int": energy[0],
        "Energy_dec": energy[1],
        "Water_int": water[0],
        "Water_dec": water[1],
    }


def _appliance(device_id: str, type_code: str, feature: str, status_list: dict) -> ConnectLifeAppliance:
    return cast(
        ConnectLifeAppliance,
        SimpleNamespace(
            device_id=device_id,
            device_type_code=type_code,
            device_feature_code=feature,
            puid=f"puid{device_id}",
            device_nickname=f"dev-{device_id}",
            status_list=status_list,
        ),
    )


def test_cycle_reading_combines_counters_and_flags_finished():
    appliance = _appliance("d", "t", "f", _status(FINISHED, energy=(1, 4), water=(43, 20)))

    is_finished, energy, water = cast(tuple, cycle_reading(appliance, _cycle_dictionary()))

    assert is_finished is True
    assert energy == pytest.approx(1.04)
    assert water == pytest.approx(43.2)
    assert cycle_reading(_appliance("d", "t", "f", _status(RUNNING)), _cycle_dictionary())[0] is False  # type: ignore[index]


def test_cycle_reading_is_none_when_not_opted_in_or_properties_missing():
    appliance = _appliance("d", "t", "f", _status(FINISHED, energy=(1, 4), water=(43, 20)))
    assert cycle_reading(appliance, _cycle_dictionary(cycle_totals=None)) is None

    no_phase = _status(FINISHED, energy=(1, 4), water=(43, 20))
    del no_phase["Phase"]
    assert cycle_reading(_appliance("d", "t", "f", no_phase), _cycle_dictionary()) is None

    no_energy = {"Phase": FINISHED, "Water_int": 1, "Water_dec": 0}
    assert cycle_reading(_appliance("d", "t", "f", no_energy), _cycle_dictionary()) is None


# -- coordinator -------------------------------------------------------------

_CYC = ("cyc_type", "cyc_feat")  # opted in to cycle totals
_CLOUD = ("cloud_type", "cloud_feat")  # cloud endpoint only


class _FakeStore:
    def __init__(self, preload: dict | None = None):
        self.preload = preload
        self.delayed: list[dict] = []
        self.saved: list[dict] = []

    async def async_load(self):
        return self.preload

    async def async_save(self, data):
        self.saved.append(data)

    def async_delay_save(self, data_func, delay=0):
        self.delayed.append(data_func())


class _FakeApi:
    def __init__(self):
        self.consumption_calls = 0

    async def get_energy_consumption_curve(self, *_args):
        self.consumption_calls += 1
        return SimpleNamespace(electric_curve={_today_key(): "1.0"}, water_curve={})


@pytest.fixture(autouse=True)
def _seed_dictionaries():
    Dictionaries.dictionaries.clear()
    Dictionaries.dictionaries[f"{_CYC[0]}-{_CYC[1]}"] = _cycle_dictionary()
    Dictionaries.dictionaries[f"{_CLOUD[0]}-{_CLOUD[1]}"] = _cycle_dictionary(cycle_totals=None)
    yield
    Dictionaries.dictionaries.clear()


def _coordinator(data: dict, store: _FakeStore | None = None, api: _FakeApi | None = None):
    # Bypass DataUpdateCoordinator.__init__ (needs hass).
    coord = ConnectLifeStatisticsCoordinator.__new__(ConnectLifeStatisticsCoordinator)
    coord.api = api or _FakeApi()  # type: ignore[assignment]
    coord.appliance_coordinator = SimpleNamespace(data=data)  # type: ignore[assignment]
    coord.cycle_totals = {}
    coord._store = store if store is not None else _FakeStore()  # type: ignore[assignment]
    coord.listener_updates = 0  # type: ignore[attr-defined]

    def _count_update():
        coord.listener_updates += 1  # type: ignore[attr-defined]

    coord.async_update_listeners = _count_update  # type: ignore[method-assign]
    return coord


def test_observe_banks_a_finished_cycle_and_notifies_sensors_and_storage():
    data = {"cyc": _appliance("cyc", *_CYC, _status(RUNNING, energy=(0, 50)))}
    store = _FakeStore()
    coord = _coordinator(data, store)

    coord._observe_cycle_totals()  # first sight: running
    data["cyc"] = _appliance("cyc", *_CYC, _status(FINISHED, energy=(1, 4), water=(43, 20)))
    coord._observe_cycle_totals()

    totals = coord.cycle_totals["cyc"]
    assert (totals.energy_kwh, totals.water_l) == (1.04, 43.2)
    assert store.delayed[-1]["cycle_totals"]["cyc"]["energy_kwh"] == 1.04
    assert coord.listener_updates == 2  # once for the new state, once for the banked cycle


def test_banking_a_cycle_is_logged_for_debugging(caplog):
    data = {"cyc": _appliance("cyc", *_CYC, _status(RUNNING, energy=(1, 4), water=(43, 20)))}
    coord = _coordinator(data)
    coord._observe_cycle_totals()
    data["cyc"] = _appliance("cyc", *_CYC, _status(FINISHED, energy=(1, 4), water=(43, 20)))

    with caplog.at_level("DEBUG", logger="custom_components.connectlife.coordinator"):
        coord._observe_cycle_totals()
        coord._observe_cycle_totals()  # unchanged: must not log again

    banked = [r.getMessage() for r in caplog.records if "Banked finished cycle" in r.getMessage()]
    assert banked == ["Banked finished cycle for dev-cyc: day total now 1.04 kWh, 43.20 L"]


def test_observe_only_notifies_and_saves_when_something_changed():
    data = {"cyc": _appliance("cyc", *_CYC, _status(RUNNING))}
    store = _FakeStore()
    coord = _coordinator(data, store)

    coord._observe_cycle_totals()
    updates, saves = coord.listener_updates, len(store.delayed)
    coord._observe_cycle_totals()  # same reading again
    coord._observe_cycle_totals()

    assert (coord.listener_updates, len(store.delayed)) == (updates, saves)


def test_observe_ignores_devices_that_have_not_opted_in():
    data = {"cloud": _appliance("cloud", *_CLOUD, _status(FINISHED, energy=(1, 4), water=(43, 20)))}
    coord = _coordinator(data)

    coord._observe_cycle_totals()

    assert coord.cycle_totals == {}
    assert coord.listener_updates == 0


async def test_cloud_endpoint_is_skipped_only_for_devices_tracking_cycle_totals():
    api = _FakeApi()
    data = {
        "cyc": _appliance("cyc", *_CYC, _status(RUNNING)),
        "cloud": _appliance("cloud", *_CLOUD, _status(RUNNING)),
    }
    coord = _coordinator(data, api=api)
    coord._observe_cycle_totals()

    result = await coord._async_update_data()

    assert set(result) == {"cloud"}
    assert api.consumption_calls == 1


async def test_device_missing_the_properties_falls_back_to_the_cloud_endpoint():
    api = _FakeApi()
    no_counters = {"Phase": RUNNING}
    coord = _coordinator({"cyc": _appliance("cyc", *_CYC, no_counters)}, api=api)
    coord._observe_cycle_totals()

    result = await coord._async_update_data()

    assert coord.cycle_totals == {}
    assert set(result) == {"cyc"}
    assert api.consumption_calls == 1


async def test_setup_restores_totals_so_a_restart_does_not_recount_a_finished_cycle():
    stored = {
        "cycle_totals": {
            "cyc": {
                "day": dt_util.now().date().isoformat(),
                "energy_kwh": 5.0,
                "water_l": 100.0,
                "banked": True,
            }
        }
    }
    data = {"cyc": _appliance("cyc", *_CYC, _status(FINISHED, energy=(1, 4), water=(43, 20)))}
    coord = _coordinator(data, _FakeStore(preload=stored))

    await coord._async_setup()

    totals = coord.cycle_totals["cyc"]
    assert (totals.energy_kwh, totals.water_l) == (5.0, 100.0)  # the finished cycle isn't added again


async def test_setup_without_stored_state_does_not_count_an_already_finished_cycle():
    data = {"cyc": _appliance("cyc", *_CYC, _status(FINISHED, energy=(1, 4), water=(43, 20)))}
    coord = _coordinator(data, _FakeStore(preload=None))

    await coord._async_setup()

    totals = coord.cycle_totals["cyc"]
    assert (totals.energy_kwh, totals.water_l, totals.banked) == (0.0, 0.0, True)


async def test_setup_survives_corrupt_stored_totals():
    stored = {"cycle_totals": {"cyc": {"day": "garbage"}}}
    data = {"cyc": _appliance("cyc", *_CYC, _status(RUNNING))}
    coord = _coordinator(data, _FakeStore(preload=stored))

    await coord._async_setup()

    assert coord.cycle_totals["cyc"].energy_kwh == 0.0  # discarded, then started fresh


def test_start_cycle_tracking_subscribes_to_the_main_coordinator_and_returns_unsubscribe():
    subscribed = []

    def unsubscribe():
        pass

    def add_listener(callback):
        subscribed.append(callback)
        return unsubscribe

    coord = _coordinator({})
    coord.appliance_coordinator = SimpleNamespace(data={}, async_add_listener=add_listener)  # type: ignore[assignment]

    assert coord.async_start_cycle_tracking() is unsubscribe
    assert subscribed == [coord._observe_cycle_totals]


# -- sensor ------------------------------------------------------------------


class _FakeStatsCoordinator:
    def __init__(self, data=None, cycle_totals=None):
        self.data = data if data is not None else {}
        self.last_update_success = True
        self.cycle_totals = cycle_totals if cycle_totals is not None else {}


def _make_sensor(coordinator, sensor_def):
    appliance_coordinator = SimpleNamespace(add_entity=lambda *a, **k: None)
    appliance = SimpleNamespace(device_id="dev1")
    return ConnectLifeStatisticsSensor(
        appliance_coordinator,  # type: ignore[arg-type]
        coordinator,  # type: ignore[arg-type]
        appliance,  # type: ignore[arg-type]
        sensor_def,
    )


_ENERGY_DEF, _WATER_DEF = ConsumptionStatisticsSource().sensors


def test_daily_sensors_use_cycle_totals_and_are_available_without_cloud_data():
    totals = DailyCycleTotals(dt_util.now().date(), energy_kwh=1.22, water_l=48.7)
    coord = _FakeStatsCoordinator(data={}, cycle_totals={"dev1": totals})

    energy = _make_sensor(coord, _ENERGY_DEF)
    water = _make_sensor(coord, _WATER_DEF)

    assert energy.native_value == 1.22
    assert water.native_value == 48.7
    assert energy.available is True and water.available is True


def test_cycle_totals_take_precedence_over_a_cloud_result():
    totals = DailyCycleTotals(dt_util.now().date(), energy_kwh=1.22, water_l=48.7)
    cloud = SimpleNamespace(electric_curve={_today_key(): "15.32"}, water_curve={})
    coord = _FakeStatsCoordinator(data={"dev1": cloud}, cycle_totals={"dev1": totals})

    assert _make_sensor(coord, _ENERGY_DEF).native_value == 1.22


def test_sensor_updates_when_a_cycle_is_banked():
    totals = DailyCycleTotals(dt_util.now().date(), energy_kwh=0.0, water_l=0.0)
    coord = _FakeStatsCoordinator(cycle_totals={"dev1": totals})
    sensor = _make_sensor(coord, _ENERGY_DEF)
    assert sensor.native_value == 0.0

    totals.energy_kwh = 1.04
    sensor._update_native_value()

    assert sensor.native_value == 1.04


def test_sensor_falls_back_to_the_cloud_result_without_cycle_totals():
    cloud = SimpleNamespace(electric_curve={_today_key(): "1.5"}, water_curve={})
    sensor = _make_sensor(_FakeStatsCoordinator(data={"dev1": cloud}), _ENERGY_DEF)

    assert sensor.native_value == 1.5
    assert sensor.available is True


def test_sensor_unavailable_with_neither_cycle_totals_nor_cloud_result():
    sensor = _make_sensor(_FakeStatsCoordinator(data={}), _ENERGY_DEF)

    assert sensor.native_value is None
    assert sensor.available is False


def test_sensors_without_a_cycle_value_ignore_cycle_totals():
    totals = DailyCycleTotals(dt_util.now().date(), energy_kwh=1.22, water_l=48.7)
    air_duct = SimpleNamespace(electric_total=2.0)
    coord = _FakeStatsCoordinator(data={"dev1": air_duct}, cycle_totals={"dev1": totals})

    sensor = _make_sensor(coord, AirDuctStatisticsSource().sensors[0])

    assert sensor.native_value == 2.0
