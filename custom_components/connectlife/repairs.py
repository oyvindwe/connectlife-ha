from __future__ import annotations

import logging

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class UnavailableDeviceRepairFlow(RepairsFlow):
    """Flow to delete unavailable device."""

    def __init__(self, issue_id: str, data: dict[str, str | int | float | None] | None) -> None:
        """Initialize repair flow."""
        self.issue_id = issue_id
        self.data = data

    async def async_step_init(
            self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of a fix flow."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["remove", "ignore"],
            description_placeholders=self.data,
        )

    async def async_step_remove(
            self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of a fix flow."""
        if user_input is not None:
            _LOGGER.info("Removing device %s", self.data["device_name"])
            dr.async_get(self.hass).async_remove_device(self.data["device_id"])
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="remove",
            description_placeholders=self.data
        )

    async def async_step_ignore(
            self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the ignore step of a fix flow."""
        ir.async_get(self.hass).async_ignore(DOMAIN, self.issue_id, True)
        return self.async_abort(
            reason="issue_ignored",
            description_placeholders=self.data
        )


async def async_create_fix_flow(
        hass: HomeAssistant,
        issue_id: str,
        data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create flow."""
    if issue_id.startswith("unavailable_device."):
        return UnavailableDeviceRepairFlow(issue_id, data)
