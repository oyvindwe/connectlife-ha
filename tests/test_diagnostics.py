"""Tests for ConnectLife diagnostics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import custom_components.connectlife.diagnostics as diagmod
from custom_components.connectlife.const import CONF_DEVICES, CONF_EXPOSE_OFFLINE_STATE


def _appliance(status_list: dict) -> SimpleNamespace:
    return SimpleNamespace(
        device_id="secret-device-id",
        device_nickname="Living room AC",
        room_name="Living room",
        device_type_code="999",
        device_type_name="Test",
        device_feature_code="000",
        device_feature_name="Test feature",
        offline_state=1,
        status_list=status_list,
    )


def test_appliance_diagnostics_reports_mapping_without_private_data(build_dictionary) -> None:
    build_dictionary(base={"properties": [{"property": "t_power", "switch": {}}]})
    appliance = _appliance({"t_power": 1, "f_unknown": 7, "mac": "aa:bb:cc"})
    entry = SimpleNamespace(
        options={CONF_DEVICES: {"secret-device-id": {CONF_EXPOSE_OFFLINE_STATE: True}}}
    )

    def fake_load(path):
        return path == "data_dictionaries/999.yaml", None

    with patch.object(diagmod, "_load_yaml", side_effect=fake_load):
        result = diagmod._appliance_diagnostics(entry, appliance)

    assert result["mapping_files"] == {"999.yaml": True, "999-000.yaml": False}
    assert result["unmapped_properties"] == ["f_unknown", "mac"]
    assert result["options"] == {CONF_EXPOSE_OFFLINE_STATE: True}
    assert result["status_list"]["mac"] == "**REDACTED**"
    text = repr(result)
    for private in ("secret-device-id", "Living room"):
        assert private not in text
