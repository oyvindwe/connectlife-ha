"""Local ConnectLife API compatibility wrapper."""

from __future__ import annotations

import logging
from typing import Any, Sequence

import aiohttp
from connectlife.api import ConnectLifeApi as UpstreamConnectLifeApi
from connectlife.api import LifeConnectAuthError, LifeConnectError
from connectlife.appliance import ConnectLifeAppliance

_LOGGER = logging.getLogger(__name__)


class ConnectLifeApi(UpstreamConnectLifeApi):
    """ConnectLife API wrapper for compatibility fixes not yet released upstream."""

    async def get_appliances_json(self) -> Any:
        """Fetch appliances with friendlier fallback logging."""
        await self._fetch_access_token()
        try:
            return await self._request_appliances_json(retry_on_reauth=True)
        except LifeConnectAuthError:
            raise
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.warning(
                "ConnectLife appliance list request failed via bapi, trying HijuConn gateway..."
            )
            return await self._request_gateway_appliances_json(retry_on_reauth=True)
        except LifeConnectError as err:
            if not self._should_fallback_to_gateway(err):
                raise
            _LOGGER.warning(
                "ConnectLife appliance list request failed via bapi, trying HijuConn gateway..."
            )
            return await self._request_gateway_appliances_json(retry_on_reauth=True)

    async def get_appliances(self) -> Sequence[ConnectLifeAppliance]:
        """Fetch appliances and tolerate payloads without a status list."""
        appliances = await self.get_appliances_json()
        parsed: list[ConnectLifeAppliance] = []

        for appliance in appliances:
            if "deviceId" not in appliance:
                continue

            raw_status_list = appliance.get("statusList")
            if not isinstance(raw_status_list, dict):
                _LOGGER.warning(
                    "ConnectLife appliance %s payload %s statusList; using empty status list",
                    appliance.get("deviceId"),
                    "is missing" if raw_status_list is None else f"has invalid {type(raw_status_list).__name__}",
                )
                appliance = {**appliance, "statusList": {}}

            parsed.append(ConnectLifeAppliance(self, appliance))

        self.appliances = parsed
        return self.appliances
