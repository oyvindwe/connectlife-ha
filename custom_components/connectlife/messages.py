"""User-facing ConnectLife status messages."""

from __future__ import annotations

GATEWAY_ERROR_PREFIX = "Unexpected response from HijuConn gateway"
NETWORK_ERROR_MARKERS = (
    "Cannot connect to host",
    "Name or service not known",
    "Temporary failure in name resolution",
    "Timeout while contacting DNS servers",
)


def format_retry_message(error: Exception) -> str:
    """Return a short retry message for Home Assistant UI surfaces."""
    message = str(error)

    if isinstance(error, TimeoutError):
        return (
            "ConnectLife request timed out. The integration will retry automatically."
        )
    if message.startswith(GATEWAY_ERROR_PREFIX):
        return (
            "ConnectLife gateway rejected the request. "
            "The integration will retry automatically."
        )
    if any(marker in message for marker in NETWORK_ERROR_MARKERS):
        return "Could not reach ConnectLife. The integration will retry automatically."
    return "ConnectLife request failed. The integration will retry automatically."
