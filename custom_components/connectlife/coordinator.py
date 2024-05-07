import async_timeout
import logging
from datetime import timedelta

from connectlife.api import LifeConnectAuthError, LifeConnectError, ConnectLifeApi
from connectlife.appliance import ConnectLifeAppliance
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

class ConnectLifeCoordinator(DataUpdateCoordinator):
    """ConnectLife coordinator."""

    _appliances: dict[str, ConnectLifeAppliance] = {}

    def __init__(self, hass, api: ConnectLifeApi):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="ConnectLife",
            update_interval=timedelta(seconds=60),
        )
        self.api = api

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                await self.api.get_appliances()
                self._appliances = {a.device_id: a for a in self.api.appliances}
        except LifeConnectAuthError as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except LifeConnectError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    @property
    def appliances(self) -> dict[str, ConnectLifeAppliance]:
        """Dictionary of device id, appliance."""
        return self._appliances
