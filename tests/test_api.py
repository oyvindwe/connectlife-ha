"""Tests for the local ConnectLife API compatibility wrapper."""

from __future__ import annotations

import importlib.util
import json
import tomllib
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
API_MODULE_PATH = ROOT / "custom_components" / "connectlife" / "api.py"
MANIFEST_PATH = ROOT / "custom_components" / "connectlife" / "manifest.json"
PYPROJECT_PATH = ROOT / "pyproject.toml"

API_SPEC = importlib.util.spec_from_file_location("connectlife_ha_local_api", API_MODULE_PATH)
if API_SPEC is None or API_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {API_MODULE_PATH}")
API_MODULE = importlib.util.module_from_spec(API_SPEC)
API_SPEC.loader.exec_module(API_MODULE)

ConnectLifeApi = API_MODULE.ConnectLifeApi


def _appliance_payload(
    *,
    device_id: str = "device-1",
    status_list: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a minimal appliance payload."""
    payload = {
        "wifiId": "wifi-1",
        "deviceId": device_id,
        "puid": "puid-1",
        "deviceNickName": "Kitchen AC",
        "deviceFeatureCode": "009-100",
        "deviceFeatureName": "Air Conditioner",
        "deviceTypeCode": "009",
        "deviceTypeName": "Air Conditioner",
        "role": 1,
        "roomId": 1,
        "roomName": "Kitchen",
        "offlineState": 0,
        "seq": 1,
        "bindTime": 0,
        "useTime": 0,
        "createTime": 0,
    }
    if status_list is not None:
        payload["statusList"] = status_list
    return payload


class ConnectLifeApiCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    """Compatibility coverage for malformed appliance payloads."""

    async def test_get_appliances_uses_empty_status_list_when_missing(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")

        with (
            patch.object(
                ConnectLifeApi,
                "get_appliances_json",
                new=AsyncMock(return_value=[_appliance_payload()]),
            ),
            self.assertLogs(API_MODULE.__name__, level="WARNING") as captured,
        ):
            appliances = await api.get_appliances()

        self.assertEqual(len(appliances), 1)
        self.assertEqual(appliances[0].device_id, "device-1")
        self.assertEqual(appliances[0].status_list, {})
        self.assertIn("payload is missing statusList", captured.output[0])


class MetadataTests(unittest.TestCase):
    """Version metadata should stay aligned across packaging files."""

    def test_manifest_and_pyproject_versions_match(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text())
        pyproject = tomllib.loads(PYPROJECT_PATH.read_text())

        self.assertEqual(pyproject["project"]["version"], manifest["version"])
