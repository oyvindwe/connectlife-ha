"""Browser sign-in (OAuth2) for ConnectLife."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    LocalOAuth2Implementation,
    OAuth2Session,
)
from aiohttp import ClientError, ClientResponseError
from connectlife.api import LifeConnectAuthError, LifeConnectError
from connectlife.oauth import (
    OAUTH2_AUTHORIZE_URL,
    OAUTH2_CLIENT_ID,
    OAUTH2_CLIENT_SECRET,
    OAUTH2_TOKEN_URL,
    OAuthConnectLifeApi,
)

from .const import CONF_SOURCE_ID, DOMAIN


class ConnectLifeOAuth2Implementation(LocalOAuth2Implementation):
    """Sign in on the ConnectLife login page with Hisense's client for Home Assistant."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            DOMAIN,
            OAUTH2_CLIENT_ID,
            OAUTH2_CLIENT_SECRET,
            OAUTH2_AUTHORIZE_URL,
            OAUTH2_TOKEN_URL,
        )

    @property
    def name(self) -> str:
        return "ConnectLife"


def create_oauth_api(entry: ConfigEntry, session: OAuth2Session) -> OAuthConnectLifeApi:
    """Create an API client using the entry's OAuth tokens, refreshed as needed."""

    async def access_token() -> str:
        try:
            await session.async_ensure_token_valid()
        except ClientResponseError as err:
            # A rejected refresh token means signing in again.
            if 400 <= err.status < 500:
                raise LifeConnectAuthError("ConnectLife sign-in expired") from err
            raise LifeConnectError(f"Could not refresh the ConnectLife token: {err}") from err
        except ClientError as err:
            raise LifeConnectError(f"Could not refresh the ConnectLife token: {err}") from err
        return session.token["access_token"]

    return OAuthConnectLifeApi(access_token, source_id=entry.data.get(CONF_SOURCE_ID))
