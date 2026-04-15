"""Tests for user-facing ConnectLife messages."""

from __future__ import annotations

from custom_components.connectlife.messages import format_retry_message


def test_gateway_rejection_uses_human_friendly_message() -> None:
    message = format_retry_message(
        Exception(
            "Unexpected response from HijuConn gateway: "
            "code=101005 description='randStr check fail!'"
        )
    )

    assert message == (
        "ConnectLife gateway rejected the request."
        " The integration will retry automatically."
    )


def test_timeout_uses_human_friendly_message() -> None:
    message = format_retry_message(TimeoutError())

    assert message == (
        "ConnectLife request timed out."
        " The integration will retry automatically."
    )


def test_network_error_uses_human_friendly_message() -> None:
    message = format_retry_message(
        Exception(
            "Cannot connect to host clife-eu-gateway.hijuconn.com:443 "
            "ssl:default [Timeout while contacting DNS servers]"
        )
    )

    assert message == (
        "Could not reach ConnectLife."
        " The integration will retry automatically."
    )


def test_unknown_error_uses_generic_message() -> None:
    message = format_retry_message(Exception("backend unavailable"))

    assert message == (
        "ConnectLife request failed."
        " The integration will retry automatically."
    )
