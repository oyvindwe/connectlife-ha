"""Tests for the Terms & Conditions login retry throttle."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from custom_components.connectlife import terms
from custom_components.connectlife.terms import (
    TERMS_NOT_ACCEPTED_RETRY_INTERVAL,
    clear_terms_retry_throttle,
    terms_accepted,
    terms_not_accepted,
    terms_retry_throttled,
)

ENTRY = SimpleNamespace(entry_id="entry-1", title="ConnectLife (user)")


def _hass() -> SimpleNamespace:
    return SimpleNamespace(data={})


@patch.object(terms.ir, "async_create_issue")
def test_throttles_until_interval_elapsed(create_issue) -> None:
    hass = _hass()
    assert not terms_retry_throttled(hass, ENTRY)  # type: ignore[arg-type]

    with patch.object(terms.time, "monotonic", return_value=1000.0):
        terms_not_accepted(hass, ENTRY)  # type: ignore[arg-type]
    create_issue.assert_called_once()

    interval = TERMS_NOT_ACCEPTED_RETRY_INTERVAL.total_seconds()
    with patch.object(terms.time, "monotonic", return_value=1000.0 + interval - 1):
        assert terms_retry_throttled(hass, ENTRY)  # type: ignore[arg-type]
    with patch.object(terms.time, "monotonic", return_value=1000.0 + interval):
        assert not terms_retry_throttled(hass, ENTRY)  # type: ignore[arg-type]


@patch.object(terms.ir, "async_create_issue")
def test_clear_lifts_throttle(_create_issue) -> None:
    hass = _hass()
    terms_not_accepted(hass, ENTRY)  # type: ignore[arg-type]
    clear_terms_retry_throttle(hass, ENTRY.entry_id)  # type: ignore[arg-type]
    assert not terms_retry_throttled(hass, ENTRY)  # type: ignore[arg-type]


@patch.object(terms.ir, "async_delete_issue")
@patch.object(terms.ir, "async_create_issue")
def test_accepted_lifts_throttle_and_deletes_issue(_create_issue, delete_issue) -> None:
    hass = _hass()
    terms_not_accepted(hass, ENTRY)  # type: ignore[arg-type]
    terms_accepted(hass, ENTRY)  # type: ignore[arg-type]
    assert not terms_retry_throttled(hass, ENTRY)  # type: ignore[arg-type]
    delete_issue.assert_called_once_with(hass, "connectlife", "terms_not_accepted.entry-1")
