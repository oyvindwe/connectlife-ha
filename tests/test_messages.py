"""Tests for user-facing ConnectLife messages."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components" / "connectlife" / "messages.py"

MODULE_SPEC = importlib.util.spec_from_file_location("connectlife_messages", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
MESSAGES_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MESSAGES_MODULE)


class FormatRetryMessageTests(unittest.TestCase):
    """Tests for user-facing retry messages."""

    def test_gateway_rejection_uses_human_friendly_message(self) -> None:
        message = MESSAGES_MODULE.format_retry_message(
            Exception(
                "Unexpected response from HijuConn gateway: "
                "code=101005 description='randStr check fail!'"
            )
        )

        self.assertEqual(
            message,
            "ConnectLife gateway rejected the request. The integration will retry automatically.",
        )

    def test_timeout_uses_human_friendly_message(self) -> None:
        message = MESSAGES_MODULE.format_retry_message(TimeoutError())

        self.assertEqual(
            message,
            "ConnectLife request timed out. The integration will retry automatically.",
        )

    def test_network_error_uses_human_friendly_message(self) -> None:
        message = MESSAGES_MODULE.format_retry_message(
            Exception(
                "Cannot connect to host clife-eu-gateway.hijuconn.com:443 "
                "ssl:default [Timeout while contacting DNS servers]"
            )
        )

        self.assertEqual(
            message,
            "Could not reach ConnectLife. The integration will retry automatically.",
        )

    def test_unknown_error_uses_generic_message(self) -> None:
        message = MESSAGES_MODULE.format_retry_message(Exception("backend unavailable"))

        self.assertEqual(
            message,
            "ConnectLife request failed. The integration will retry automatically.",
        )


if __name__ == "__main__":
    unittest.main()
