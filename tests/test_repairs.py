"""Tests for the repair flows."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.connectlife.const import CONF_DEVICES, CONF_DISABLE_BEEP, DOMAIN
from custom_components.connectlife.repairs import UnsupportedBeepRepairFlow


async def test_unsupported_beep_repair_reloads_entry(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, options={CONF_DEVICES: {"device-1": {CONF_DISABLE_BEEP: True}}}
    )
    entry.add_to_hass(hass)
    flow = UnsupportedBeepRepairFlow(
        "unsupported_beep.device-1", {"entry_id": entry.entry_id, "device_id": "device-1"}
    )
    flow.hass = hass

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        await flow.async_step_confirm()

    assert entry.options[CONF_DEVICES]["device-1"][CONF_DISABLE_BEEP] is False
    schedule_reload.assert_called_once_with(entry.entry_id)
