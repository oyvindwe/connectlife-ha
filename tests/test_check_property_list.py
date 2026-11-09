"""Tests for scripts/check_property_list.py."""

from __future__ import annotations

import pytest

from scripts.check_property_list import check, parse_values


@pytest.mark.parametrize(
    ("value_list", "expected"),
    [
        ("0,1", ({0, 1}, False)),
        ("0:close,1:auto,2:less", ({0, 1, 2}, False)),
        ("0: Disable\n1: Enable，2:notdisplay", ({0, 1, 2}, False)),
        ("0close，1:1；2：2；3：3", ({0, 1, 2, 3}, False)),
        ("0:close,1:ironing,2:wear,3:save,4:performance,Other:DryTime", ({0, 1, 2, 3, 4}, True)),
        ("1：Cupboard Dry。2：Iron Dry。3：Cupboard Dry Extra。大于等于5表示实际烘干时间。", ({1, 2, 3}, True)),
        ("3096,3297", ({3096, 3297}, False)),
        ("SelectedProgramId", (None, True)),
        (None, (None, True)),
    ],
)
def test_parse_values(value_list, expected) -> None:
    assert parse_values(value_list) == expected


def _entry(key: str, read_write: str = "RW", values: str | None = None, low="null", high="null") -> dict:
    return {
        "propertyKey": key,
        "propertyRW": read_write,
        "propertyValueList": values,
        "lowerLimit": low,
        "upperLimit": high,
    }


def test_check_findings(build_mapping) -> None:
    build_mapping(
        base={
            "properties": [
                {"property": "t_mode", "select": {"options": {0: "auto", 1: "low", 9: "high"}}},
                {"property": "t_switch", "switch": {}},
                {"property": "t_cmd", "switch": {"command": {"name": "SET_CMD"}}},
                {"property": "t_temp", "number": {"min_value": 0, "max_value": 9}},
                {"property": "f_state", "sensor": {"device_class": "enum", "options": {0: "off", 1: "on"}}},
            ]
        }
    )
    findings = check("999", "000", {
        "properties": [
            _entry("t_mode", values="0:auto,1:low,2:high"),
            _entry("t_switch", read_write="R", values="0,1"),
            _entry("t_cmd", read_write="R", values="0,1"),
            _entry("t_temp", low="2", high="8"),
            _entry("f_state", read_write="R", values="0,1,2"),
        ]
    })
    kinds = {(kind, name) for kind, name, _ in findings}
    assert kinds == {
        ("OPTION", "t_mode"),  # 9 isn't in the list
        ("MISSING", "t_mode"),  # 2 isn't mapped
        ("READONLY", "t_switch"),  # t_cmd is written through its command
        ("RANGE", "t_temp"),
        ("MISSING", "f_state"),
    }
