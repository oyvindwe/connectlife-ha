"""Handling of logins rejected until updated Terms & Conditions are accepted."""

from __future__ import annotations

import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

# Logging in can't succeed until the user accepts the terms in the ConnectLife app,
# so only attempt it this often instead of on every setup retry or poll.
TERMS_NOT_ACCEPTED_RETRY_INTERVAL = timedelta(minutes=15)

# hass.data key: entry_id -> time.monotonic() of the last rejected login.
DATA_TERMS_NOT_ACCEPTED = f"{DOMAIN}_terms_not_accepted"

ISSUE_ID_PREFIX = "terms_not_accepted."


def terms_retry_throttled(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Return True if a login was rejected for this entry too recently to retry."""
    rejected_at = hass.data.get(DATA_TERMS_NOT_ACCEPTED, {}).get(entry.entry_id)
    return (
        rejected_at is not None
        and time.monotonic() - rejected_at < TERMS_NOT_ACCEPTED_RETRY_INTERVAL.total_seconds()
    )


def clear_terms_retry_throttle(hass: HomeAssistant, entry_id: str) -> None:
    """Allow the next setup or poll to attempt a login right away."""
    hass.data.get(DATA_TERMS_NOT_ACCEPTED, {}).pop(entry_id, None)


def terms_not_accepted(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Record a rejected login and create the repair issue explaining how to fix it."""
    hass.data.setdefault(DATA_TERMS_NOT_ACCEPTED, {})[entry.entry_id] = time.monotonic()
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_ID_PREFIX}{entry.entry_id}",
        data={"entry_id": entry.entry_id, "title": entry.title},
        is_fixable=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="terms_not_accepted",
        translation_placeholders={"title": entry.title},
    )


def terms_accepted(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear the throttle and repair issue once a login succeeds."""
    clear_terms_retry_throttle(hass, entry.entry_id)
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_ID_PREFIX}{entry.entry_id}")
