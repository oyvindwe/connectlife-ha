import async_timeout
import logging
from datetime import timedelta

from connectlife.api import LifeConnectAuthError, LifeConnectError, ConnectLifeApi
from connectlife.appliance import ConnectLifeAppliance
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

MAX_RETRIES = 3

_LOGGER = logging.getLogger(__name__)

class ConnectLifeCoordinator(DataUpdateCoordinator[dict[str, ConnectLifeAppliance]]):
    """ConnectLife coordinator."""

    # We need initial data, so no retries for first request.
    error_count = MAX_RETRIES

    def __init__(self, hass, api: ConnectLifeApi):
        """Initialize coordinator."""
        self.api = api
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                await self.api.get_appliances()
                self.error_count = 0
        except LifeConnectAuthError as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except TimeoutError as err:
            self.error_count += 1
            i = MAX_RETRIES - self.error_count
            if i > 0:
                _LOGGER.warning(
                    "ConnectLife API request timed out, will try %d more %s",
                    i,
                    "time" if i == 1 else "times",
                )
            else:
                raise err
        except LifeConnectError as err:
            self.error_count += 1
            i = MAX_RETRIES - self.error_count
            if i > 0:
                _LOGGER.warning(
                    "ConnectLife API failed with '%s', will try %d more %s",
                    err,
                    i,
                    "time" if i == 1 else "times",
                )
            else:
                raise UpdateFailed(f"Error communicating with API: {err}")
        return {a.device_id: a for a in self.api.appliances}

    async def async_update_device(self, device_id: str, properties: dict[str, int | str]):
        """Updates the device, and sets the same data in local copy and notify to avoid refetching."""
        await self.api.update_appliance(self.data[device_id].puid, {k: str(v) for k, v in properties.items()})
        self.data[device_id].status_list.update(properties)
        self.async_update_listeners()
