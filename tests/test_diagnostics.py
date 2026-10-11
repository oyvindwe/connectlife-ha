"""Tests for ConnectLife diagnostics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from connectlife.api import LifeConnectError

import custom_components.connectlife.diagnostics as diagmod
from connectlife.api import EnergyConsumption

from custom_components.connectlife.const import CONF_DEVICES, CONF_EXPOSE_OFFLINE_STATE, DOMAIN


def _appliance(status_list: dict) -> SimpleNamespace:
    return SimpleNamespace(
        device_id="secret-device-id",
        puid="secret-puid",
        wifi_id="secret-wifi-id",
        device_nickname="Living room AC",
        room_name="Living room",
        device_type_code="999",
        device_type_name="Test",
        device_feature_code="000",
        device_feature_name="Test feature",
        offline_state=1,
        status_list=status_list,
    )


def _hass(statistics_coordinator=None) -> SimpleNamespace:
    data = {} if statistics_coordinator is None else {"entry-1_statistics": statistics_coordinator}
    return SimpleNamespace(data={DOMAIN: data})


class _FakeApi:
    def __init__(self, static_data=None, error=None):
        self.static_data = static_data
        self.error = error
        self.puids: list[str] = []

    async def query_static_data(self, puid):
        self.puids.append(puid)
        if self.error is not None:
            raise self.error
        return self.static_data


async def test_appliance_diagnostics_reports_mapping_without_private_data(build_dictionary) -> None:
    build_dictionary(base={"properties": [{"property": "t_power", "switch": {}}]})
    appliance = _appliance({"t_power": 1, "f_unknown": 7, "mac": "aa:bb:cc"})
    entry = SimpleNamespace(
        entry_id="entry-1",
        options={CONF_DEVICES: {"secret-device-id": {CONF_EXPOSE_OFFLINE_STATE: True}}},
    )

    def fake_load(path):
        return path == "data_dictionaries/999.yaml", None

    with patch.object(diagmod, "_load_yaml", side_effect=fake_load):
        result = await diagmod._appliance_diagnostics(_hass(), entry, _FakeApi({}), appliance)

    assert result["mapping_files"] == {"999.yaml": True, "999-000.yaml": False}
    assert result["unmapped_properties"] == ["f_unknown", "mac"]
    assert result["options"] == {CONF_EXPOSE_OFFLINE_STATE: True}
    assert result["status_list"]["mac"] == "**REDACTED**"
    text = repr(result)
    for private in ("secret-device-id", "Living room"):
        assert private not in text


async def test_static_data_is_included_without_identifiers() -> None:
    appliance = _appliance({})
    api = _FakeApi({
        "resultCode": 0,
        "puid": "secret-puid",
        "wifi_id": "secret-wifi-id",
        "device_id": None,
        "dev_type": "999",
        "data": {"Actions_start": "1", "echo": "secret-device-id", "Mcu_sw_version_major": "\u0000\u0000Z"},
    })

    result = diagmod.async_redact_data(await diagmod._static_data(api, appliance), diagmod.TO_REDACT)

    assert api.puids == ["secret-puid"]
    assert result["data"]["Actions_start"] == "1"
    assert result["data"]["Mcu_sw_version_major"] == "\u0000\u0000Z"
    assert result["data"]["echo"] == "**REDACTED**"
    assert "secret" not in repr(result)


async def test_static_data_error_is_reported() -> None:
    api = _FakeApi(error=LifeConnectError("Unexpected response from HijuConn gateway: code=1"))

    result = await diagmod._static_data(api, _appliance({}))

    assert result == {"error": "Unexpected response from HijuConn gateway: code=1"}


ENTRY = SimpleNamespace(entry_id="entry-1", options={})


def test_statistics_report_the_last_result_without_identifiers() -> None:
    result = EnergyConsumption(
        stat_type="week", date_start="2026-10-05", date_end="2026-10-11",
        electric_total=5.0, electric_curve={"2026-10-11": "0.5"},
        raw={"electricUsage": "5.00", "echo": "secret-puid"},
        water_total=55.0, run_time=None, cycles=None,
        norm_electric_total=None, norm_water_total=None,
        water_curve={}, energy_period=[],
    )
    coordinator = SimpleNamespace(last_update_success=True, data={"secret-device-id": result})

    statistics = diagmod._statistics(_hass(coordinator), ENTRY, _appliance({}), "energy_consumption_curve")

    assert statistics["source"] == "energy_consumption_curve"
    assert statistics["last_update_success"] is True
    assert statistics["result"]["electric_total"] == 5.0
    assert statistics["result"]["raw"]["echo"] == "**REDACTED**"


def test_statistics_without_data_report_none() -> None:
    coordinator = SimpleNamespace(last_update_success=True, data={"secret-device-id": None})

    statistics = diagmod._statistics(_hass(coordinator), ENTRY, _appliance({}), "energy_consumption_curve")

    assert statistics == {"source": "energy_consumption_curve", "last_update_success": True, "result": None}


def test_statistics_absent_without_source() -> None:
    assert diagmod._statistics(_hass(), ENTRY, _appliance({}), None) is None
