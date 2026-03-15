"""Local ConnectLife API wrapper with extra resilience for flaky upstream endpoints."""

from __future__ import annotations

import datetime as dt
import json
import logging
import asyncio
from typing import Any, Sequence

import aiohttp

from connectlife.appliance import ConnectLifeAppliance

_LOGGER = logging.getLogger(__name__)

TRANSIENT_STATUSES = frozenset({401, 403, 500, 502, 503, 504})
AUTH_TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})
BAPI_USER_AGENT = "connectlife-api-connector 2.1.4"


class LifeConnectError(Exception):
    """Base ConnectLife API error."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.endpoint = endpoint


class LifeConnectAuthError(LifeConnectError):
    """Authentication failure against ConnectLife."""


class ConnectLifeApi:
    """ConnectLife API client."""

    api_key = "4_yhTWQmHFpZkQZDSV1uV-_A"
    client_id = "5065059336212"
    client_secret = "07swfKgvJhC3ydOUS9YV_SwVz0i4LKqlOLGNUukYHVMsJRF1b-iWeUGcNlXyYCeK"

    login_url = "https://accounts.eu1.gigya.com/accounts.login"
    jwt_url = "https://accounts.eu1.gigya.com/accounts.getJWT"

    oauth2_redirect = "https://api.connectlife.io/swagger/oauth2-redirect.html"
    oauth2_authorize = "https://oauth.hijuconn.com/oauth/authorize"
    oauth2_token = "https://oauth.hijuconn.com/oauth/token"

    appliances_url = "https://connectlife.bapi.ovh/appliances"
    request_timeout = aiohttp.ClientTimeout(total=30)

    def __init__(self, username: str, password: str, test_server: str | None = None):
        """Initialize the client."""
        if test_server:
            self.login_url = f"{test_server}/accounts.login"
            self.jwt_url = f"{test_server}/accounts.getJWT"
            self.oauth2_redirect = f"{test_server}/swagger/oauth2-redirect.html"
            self.oauth2_authorize = f"{test_server}/oauth/authorize"
            self.oauth2_token = f"{test_server}/oauth/token"
            self.appliances_url = f"{test_server}/appliances"

        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._expires: dt.datetime | None = None
        self._refresh_token: str | None = None
        self._refresh_token_expires: dt.datetime | None = None
        self.appliances: Sequence[ConnectLifeAppliance] = []

    async def authenticate(self) -> bool:
        """Test whether the full ConnectLife login flow succeeds."""
        try:
            await self.login()
        except LifeConnectAuthError:
            return False
        return True

    async def login(self) -> None:
        """Force a fresh login."""
        self._reset_tokens()
        await self._fetch_access_token()

    async def get_appliances(self) -> Sequence[ConnectLifeAppliance]:
        """Fetch appliances and update the cached appliance list."""
        appliances = await self.get_appliances_json()
        self.appliances = [ConnectLifeAppliance(self, a) for a in appliances if "deviceId" in a]
        return self.appliances

    async def get_appliances_json(self) -> Any:
        """Fetch the appliance list as JSON."""
        await self._fetch_access_token()
        return await self._request_appliances_json(retry_on_reauth=True)

    async def update_appliance(self, puid: str, properties: dict[str, str]) -> None:
        """Update an appliance."""
        data = {
            "puid": puid,
            "properties": properties,
        }
        await self._fetch_access_token()
        await self._update_bapi_appliance(data)

    async def _request_appliances_json(self, *, retry_on_reauth: bool) -> Any:
        async with self._client_session() as session:
            async with session.get(
                self.appliances_url,
                headers={
                    "User-Agent": BAPI_USER_AGENT,
                    "X-Token": self._require_access_token(),
                },
            ) as response:
                if response.status != 200:
                    body = await self._read_response_body(response)
                    if retry_on_reauth and response.status in TRANSIENT_STATUSES:
                        _LOGGER.warning(
                            "ConnectLife appliances request failed with status=%s, retrying after re-authentication",
                            response.status,
                        )
                        await self.login()
                        return await self._request_appliances_json(retry_on_reauth=False)
                    raise self._response_error(
                        "Unexpected response: status={status}",
                        response,
                        body,
                        endpoint=self.appliances_url,
                    )
                return await response.json()

    async def _update_bapi_appliance(self, data: dict[str, Any]) -> None:
        async with self._client_session() as session:
            async with session.post(
                self.appliances_url,
                json=data,
                headers={
                    "User-Agent": BAPI_USER_AGENT,
                    "X-Token": self._require_access_token(),
                },
            ) as response:
                if response.status != 200:
                    body = await self._read_response_body(response)
                    raise self._response_error(
                        "Unexpected response: status={status}",
                        response,
                        body,
                        endpoint=self.appliances_url,
                    )
                result = await response.text()
                _LOGGER.debug(result)

    async def _fetch_access_token(self) -> None:
        now = dt.datetime.now()
        if self._expires is None or self._access_token is None:
            await self._initial_access_token_with_retry()
            return

        if self._expires >= now:
            return

        if self._refresh_token is None or (
            self._refresh_token_expires is not None and self._refresh_token_expires <= now
        ):
            self._reset_tokens()
            await self._initial_access_token_with_retry()
            return

        try:
            await self._refresh_access_token()
        except LifeConnectAuthError as err:
            _LOGGER.warning(
                "ConnectLife token refresh failed, retrying full login: %s",
                err,
            )
            self._reset_tokens()
            await self._initial_access_token_with_retry()

    async def _initial_access_token_with_retry(self) -> None:
        attempts = 2
        for attempt in range(1, attempts + 1):
            try:
                await self._initial_access_token()
                return
            except (aiohttp.ClientError, TimeoutError) as err:
                if attempt == attempts:
                    raise LifeConnectAuthError(
                        f"Unexpected error during login: {err}"
                    ) from err
                _LOGGER.warning(
                    "ConnectLife login attempt %d/%d failed with transport error, retrying: %s",
                    attempt,
                    attempts,
                    err,
                )
            except LifeConnectAuthError as err:
                if attempt == attempts or err.status not in AUTH_TRANSIENT_STATUSES:
                    raise
                _LOGGER.warning(
                    "ConnectLife login attempt %d/%d failed with transient auth error, retrying: %s",
                    attempt,
                    attempts,
                    err,
                )
            self._reset_tokens()
            await asyncio.sleep(2)

    async def _initial_access_token(self) -> None:
        async with self._client_session() as session:
            uid, login_token = await self._login_to_gigya(session)
            id_token = await self._fetch_jwt(session, login_token)
            code = await self._authorize(session, uid, id_token)
            await self._exchange_authorization_code(session, code)

    async def _login_to_gigya(self, session: aiohttp.ClientSession) -> tuple[str, str]:
        async with session.post(
            self.login_url,
            data={
                "loginID": self._username,
                "password": self._password,
                "APIKey": self.api_key,
            },
        ) as response:
            if response.status != 200:
                body = await self._read_response_body(response)
                raise self._response_error(
                    "Unexpected response from login: status={status}",
                    response,
                    body,
                    endpoint=self.login_url,
                    auth=True,
                )
            body = await self._json(response)
            error_code = body.get("errorCode")
            error_message = body.get("errorMessage")
            error_details = body.get("errorDetails")
            if error_code or error_message or error_details:
                raise LifeConnectAuthError(
                    (
                        "Failed to login. Code: "
                        f"{error_code} Message: '{error_message}' Details: '{error_details}'"
                    )
                )

            uid = self._require_auth_field(body, "UID")
            session_info = self._require_auth_field(body, "sessionInfo")
            if "cookieValue" not in session_info:
                _LOGGER.info("Missing 'sessionInfo.cookieValue' in response: %s", body)
                raise LifeConnectAuthError("Missing 'sessionInfo.cookieValue' in response")
            return uid, session_info["cookieValue"]

    async def _fetch_jwt(self, session: aiohttp.ClientSession, login_token: str) -> str:
        async with session.post(
            self.jwt_url,
            data={
                "APIKey": self.api_key,
                "login_token": login_token,
            },
        ) as response:
            if response.status != 200:
                body = await self._read_response_body(response)
                raise self._response_error(
                    "Unexpected response from getJWT: status={status}",
                    response,
                    body,
                    endpoint=self.jwt_url,
                    auth=True,
                )
            body = await self._json(response)
            return self._require_auth_field(body, "id_token")

    async def _authorize(
        self,
        session: aiohttp.ClientSession,
        uid: str,
        id_token: str,
    ) -> str:
        async with session.post(
            self.oauth2_authorize,
            json={
                "client_id": self.client_id,
                "redirect_uri": self.oauth2_redirect,
                "idToken": id_token,
                "response_type": "code",
                "thirdType": "CDC",
                "thirdClientId": uid,
            },
        ) as response:
            if response.status != 200:
                body = await self._read_response_body(response)
                raise self._response_error(
                    "Unexpected response from authorize: status={status}",
                    response,
                    body,
                    endpoint=self.oauth2_authorize,
                    auth=True,
                )
            body = await response.json()
            return self._require_auth_field(body, "code")

    async def _exchange_authorization_code(
        self,
        session: aiohttp.ClientSession,
        code: str,
    ) -> None:
        async with session.post(
            self.oauth2_token,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.oauth2_redirect,
                "grant_type": "authorization_code",
                "code": code,
            },
        ) as response:
            if response.status != 200:
                body = await self._read_response_body(response)
                raise self._response_error(
                    "Unexpected response from initial access token: status={status}",
                    response,
                    body,
                    endpoint=self.oauth2_token,
                    auth=True,
                )
            body = await self._json(response)
            self._set_token_state(body)

    async def _refresh_access_token(self) -> None:
        async with self._client_session() as session:
            async with session.post(
                self.oauth2_token,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.oauth2_redirect,
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
            ) as response:
                if response.status != 200:
                    body = await self._read_response_body(response)
                    raise self._response_error(
                        "Unexpected response from refreshing access token: status={status}",
                        response,
                        body,
                        endpoint=self.oauth2_token,
                        auth=True,
                    )
                body = await response.json()
                self._set_token_state(body)

    def _set_token_state(self, response: dict[str, Any]) -> None:
        self._access_token = self._require_auth_field(response, "access_token")
        expires_in = int(self._require_auth_field(response, "expires_in"))
        # Renew 90 seconds before expiration.
        self._expires = dt.datetime.now() + dt.timedelta(seconds=expires_in - 90)
        self._refresh_token = response.get("refresh_token", self._refresh_token)
        self._refresh_token_expires = self._parse_refresh_token_expiry(
            response.get("refreshTokenExpiredTime")
        )

    def _reset_tokens(self) -> None:
        self._access_token = None
        self._expires = None
        self._refresh_token = None
        self._refresh_token_expires = None

    def _require_access_token(self) -> str:
        if self._access_token is None:
            raise LifeConnectAuthError("Missing 'access_token' in response")
        return self._access_token

    def _client_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(timeout=self.request_timeout)

    @staticmethod
    async def _json(response: aiohttp.ClientResponse) -> Any:
        text = await response.text()
        _LOGGER.debug("response: %s", text)
        return json.loads(text)

    @staticmethod
    async def _read_response_body(response: aiohttp.ClientResponse) -> str:
        text = await response.text()
        _LOGGER.debug("Response status code: %s", response.status)
        _LOGGER.debug(response.headers)
        _LOGGER.debug(text)
        return text

    @staticmethod
    def _require_auth_field(response: dict[str, Any], field: str) -> Any:
        if field not in response:
            _LOGGER.info("Missing '%s' in response: %s", field, response)
            raise LifeConnectAuthError(f"Missing '{field}' in response")
        return response[field]

    @staticmethod
    def _parse_refresh_token_expiry(value: Any) -> dt.datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(float(value) / 1000)
        if isinstance(value, str):
            if value.isdigit():
                return dt.datetime.fromtimestamp(int(value) / 1000)
            try:
                return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                _LOGGER.debug("Unable to parse refreshTokenExpiredTime=%s", value)
        return None

    @staticmethod
    def _response_error(
        message_template: str,
        response: aiohttp.ClientResponse,
        body: str,
        *,
        endpoint: str,
        auth: bool = False,
    ) -> LifeConnectError:
        message = message_template.format(status=response.status)
        if body:
            _LOGGER.debug("ConnectLife error body from %s: %s", endpoint, body)
        error_type = LifeConnectAuthError if auth else LifeConnectError
        return error_type(message, status=response.status, endpoint=endpoint)
