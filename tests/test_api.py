"""Tests for the local ConnectLife API wrapper."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
from typing import Any
import unittest
from unittest.mock import patch


API_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "custom_components" / "connectlife" / "api.py"
)
API_SPEC = importlib.util.spec_from_file_location("connectlife_local_api", API_MODULE_PATH)
if API_SPEC is None or API_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {API_MODULE_PATH}")
API_MODULE = importlib.util.module_from_spec(API_SPEC)
API_SPEC.loader.exec_module(API_MODULE)

ConnectLifeApi = API_MODULE.ConnectLifeApi
RequestStep = tuple[str, str, "FakeResponse | Exception"]


class FakeResponse:
    """Minimal aiohttp response stand-in."""

    def __init__(self, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {}
        self._payload = payload

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def text(self) -> str:
        if isinstance(self._payload, str):
            return self._payload
        return json.dumps(self._payload)

    async def json(self) -> Any:
        if isinstance(self._payload, str):
            return json.loads(self._payload)
        return self._payload


class FakeSession:
    """Minimal aiohttp ClientSession stand-in."""

    def __init__(self, requests: list[RequestStep]) -> None:
        self._requests = requests

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, url: str, **kwargs) -> FakeResponse:
        return self._next("GET", url)

    def post(self, url: str, **kwargs) -> FakeResponse:
        return self._next("POST", url)

    def _next(self, method: str, url: str) -> FakeResponse:
        if not self._requests:
            raise AssertionError(f"Unexpected {method} request to {url}")

        expected_method, expected_url, response = self._requests.pop(0)
        if expected_method != method or expected_url != url:
            raise AssertionError(
                f"Expected {expected_method} {expected_url}, got {method} {url}"
            )
        if isinstance(response, Exception):
            raise response
        return response


class FakeClientSessionFactory:
    """Factory returning fake sessions that share one scripted request queue."""

    def __init__(self, requests: list[RequestStep]) -> None:
        self._requests = requests

    def __call__(self, *args, **kwargs) -> FakeSession:
        return FakeSession(self._requests)


class ConnectLifeApiTests(unittest.IsolatedAsyncioTestCase):
    """Tests for auth and request recovery paths."""

    async def test_refresh_failure_falls_back_to_full_login(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")
        api._access_token = "expired-token"
        api._refresh_token = "expired-refresh"
        api._expires = dt.datetime.now() - dt.timedelta(seconds=1)

        requests: list[RequestStep] = [
            (
                "POST",
                api.oauth2_token,
                FakeResponse(500, {"error": "temporary failure"}),
            ),
            (
                "POST",
                api.login_url,
                FakeResponse(
                    200,
                    {"UID": "uid-1", "sessionInfo": {"cookieValue": "login-token"}},
                ),
            ),
            ("POST", api.jwt_url, FakeResponse(200, {"id_token": "jwt-token"})),
            ("POST", api.oauth2_authorize, FakeResponse(200, {"code": "auth-code"})),
            (
                "POST",
                api.oauth2_token,
                FakeResponse(
                    200,
                    {
                        "access_token": "new-access-token",
                        "expires_in": 3600,
                        "refresh_token": "new-refresh-token",
                        "refreshTokenExpiredTime": 4_102_444_800_000,
                    },
                ),
            ),
        ]

        with patch.object(
            API_MODULE.aiohttp,
            "ClientSession",
            new=FakeClientSessionFactory(requests),
        ):
            await api._fetch_access_token()

        self.assertEqual(api._access_token, "new-access-token")
        self.assertEqual(api._refresh_token, "new-refresh-token")
        self.assertGreater(api._expires, dt.datetime.now())
        self.assertFalse(requests)

    async def test_initial_login_retries_after_transient_auth_error(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")

        requests: list[RequestStep] = [
            (
                "POST",
                api.login_url,
                FakeResponse(500, {"error": "upstream login error"}),
            ),
            (
                "POST",
                api.login_url,
                FakeResponse(
                    200,
                    {"UID": "uid-1", "sessionInfo": {"cookieValue": "login-token"}},
                ),
            ),
            ("POST", api.jwt_url, FakeResponse(200, {"id_token": "jwt-token"})),
            ("POST", api.oauth2_authorize, FakeResponse(200, {"code": "auth-code"})),
            (
                "POST",
                api.oauth2_token,
                FakeResponse(
                    200,
                    {
                        "access_token": "new-access-token",
                        "expires_in": 3600,
                        "refresh_token": "new-refresh-token",
                    },
                ),
            ),
        ]

        with patch.object(
            API_MODULE.aiohttp,
            "ClientSession",
            new=FakeClientSessionFactory(requests),
        ):
            with patch.object(API_MODULE.asyncio, "sleep", return_value=None):
                await api.login()

        self.assertEqual(api._access_token, "new-access-token")
        self.assertFalse(requests)

    async def test_initial_login_falls_back_to_official_oauth_profile(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")

        requests: list[RequestStep] = [
            (
                "POST",
                api.login_url,
                FakeResponse(
                    200,
                    {"UID": "uid-1", "sessionInfo": {"cookieValue": "login-token"}},
                ),
            ),
            ("POST", api.jwt_url, FakeResponse(200, {"id_token": "jwt-token"})),
            (
                "POST",
                api.oauth2_authorize,
                FakeResponse(500, {"error": "legacy oauth unavailable"}),
            ),
            (
                "POST",
                api.login_url,
                FakeResponse(
                    200,
                    {"UID": "uid-1", "sessionInfo": {"cookieValue": "login-token"}},
                ),
            ),
            ("POST", api.jwt_url, FakeResponse(200, {"id_token": "jwt-token"})),
            (
                "POST",
                api.oauth2_authorize,
                FakeResponse(500, {"error": "legacy oauth unavailable"}),
            ),
            (
                "POST",
                api.login_url,
                FakeResponse(
                    200,
                    {"UID": "uid-1", "sessionInfo": {"cookieValue": "login-token"}},
                ),
            ),
            ("POST", api.jwt_url, FakeResponse(200, {"id_token": "jwt-token"})),
            ("POST", api.oauth2_authorize, FakeResponse(200, {"code": "auth-code"})),
            (
                "POST",
                api.oauth2_token,
                FakeResponse(
                    200,
                    {
                        "access_token": "official-access-token",
                        "expires_in": 3600,
                        "refresh_token": "official-refresh-token",
                    },
                ),
            ),
        ]

        authorize_payloads: list[dict[str, Any]] = []
        token_payloads: list[dict[str, Any]] = []

        def record_post(self, url: str, **kwargs):
            if url == api.oauth2_authorize and "json" in kwargs:
                authorize_payloads.append(kwargs["json"])
            if url == api.oauth2_token and "data" in kwargs:
                token_payloads.append(kwargs["data"])
            return FakeSession._next(self, "POST", url)

        with patch.object(
            API_MODULE.aiohttp,
            "ClientSession",
            new=FakeClientSessionFactory(requests),
        ):
            with patch.object(FakeSession, "post", new=record_post):
                await api.login()

        self.assertEqual(api._access_token, "official-access-token")
        self.assertEqual(api._refresh_token, "official-refresh-token")
        self.assertEqual(authorize_payloads[0]["client_id"], API_MODULE.LEGACY_OAUTH_PROFILE.client_id)
        self.assertEqual(authorize_payloads[0]["redirect_uri"], API_MODULE.LEGACY_OAUTH_PROFILE.redirect_uri)
        self.assertEqual(authorize_payloads[1]["client_id"], API_MODULE.LEGACY_OAUTH_PROFILE.client_id)
        self.assertEqual(authorize_payloads[1]["redirect_uri"], API_MODULE.LEGACY_OAUTH_PROFILE.redirect_uri)
        self.assertEqual(authorize_payloads[2]["client_id"], API_MODULE.OFFICIAL_OAUTH_PROFILE.client_id)
        self.assertEqual(authorize_payloads[2]["redirect_uri"], API_MODULE.OFFICIAL_OAUTH_PROFILE.redirect_uri)
        self.assertEqual(token_payloads[0]["client_id"], API_MODULE.OFFICIAL_OAUTH_PROFILE.client_id)
        self.assertEqual(token_payloads[0]["client_secret"], API_MODULE.OFFICIAL_OAUTH_PROFILE.client_secret)
        self.assertFalse(requests)

    async def test_initial_login_non_transient_auth_error_does_not_fall_back_to_official_oauth_profile(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")

        requests: list[RequestStep] = [
            (
                "POST",
                api.login_url,
                FakeResponse(
                    200,
                    {"UID": "uid-1", "sessionInfo": {"cookieValue": "login-token"}},
                ),
            ),
            ("POST", api.jwt_url, FakeResponse(200, {"id_token": "jwt-token"})),
            (
                "POST",
                api.oauth2_authorize,
                FakeResponse(400, {"error": "bad request"}),
            ),
        ]

        authorize_payloads: list[dict[str, Any]] = []

        def record_post(self, url: str, **kwargs):
            if url == api.oauth2_authorize and "json" in kwargs:
                authorize_payloads.append(kwargs["json"])
            return FakeSession._next(self, "POST", url)

        with patch.object(
            API_MODULE.aiohttp,
            "ClientSession",
            new=FakeClientSessionFactory(requests),
        ):
            with patch.object(FakeSession, "post", new=record_post):
                with self.assertRaises(API_MODULE.LifeConnectAuthError) as ctx:
                    await api.login()

        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(len(authorize_payloads), 1)
        self.assertEqual(authorize_payloads[0]["client_id"], API_MODULE.LEGACY_OAUTH_PROFILE.client_id)
        self.assertFalse(requests)

    async def test_appliances_request_reauths_after_transient_server_error(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")
        api._access_token = "cached-access-token"
        api._expires = dt.datetime.now() + dt.timedelta(minutes=5)

        requests: list[RequestStep] = [
            (
                "GET",
                api.appliances_url,
                FakeResponse(500, {"error": "backend unavailable"}),
            ),
            (
                "POST",
                api.login_url,
                FakeResponse(
                    200,
                    {"UID": "uid-1", "sessionInfo": {"cookieValue": "login-token"}},
                ),
            ),
            ("POST", api.jwt_url, FakeResponse(200, {"id_token": "jwt-token"})),
            ("POST", api.oauth2_authorize, FakeResponse(200, {"code": "auth-code"})),
            (
                "POST",
                api.oauth2_token,
                FakeResponse(
                    200,
                    {
                        "access_token": "replacement-access-token",
                        "expires_in": 3600,
                        "refresh_token": "replacement-refresh-token",
                    },
                ),
            ),
            (
                "GET",
                api.appliances_url,
                FakeResponse(200, [{"deviceId": "device-1"}]),
            ),
        ]

        with patch.object(
            API_MODULE.aiohttp,
            "ClientSession",
            new=FakeClientSessionFactory(requests),
        ):
            result = await api.get_appliances_json()

        self.assertEqual(result, [{"deviceId": "device-1"}])
        self.assertEqual(api._access_token, "replacement-access-token")
        self.assertFalse(requests)

    async def test_appliances_request_401_does_not_fallback_to_gateway_after_reauth(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")
        api._access_token = "cached-access-token"
        api._expires = dt.datetime.now() + dt.timedelta(minutes=5)

        requests: list[RequestStep] = [
            (
                "GET",
                api.appliances_url,
                FakeResponse(401, {"error": "expired token"}),
            ),
            (
                "POST",
                api.login_url,
                FakeResponse(
                    200,
                    {"UID": "uid-1", "sessionInfo": {"cookieValue": "login-token"}},
                ),
            ),
            ("POST", api.jwt_url, FakeResponse(200, {"id_token": "jwt-token"})),
            ("POST", api.oauth2_authorize, FakeResponse(200, {"code": "auth-code"})),
            (
                "POST",
                api.oauth2_token,
                FakeResponse(
                    200,
                    {
                        "access_token": "replacement-access-token",
                        "expires_in": 3600,
                        "refresh_token": "replacement-refresh-token",
                    },
                ),
            ),
            (
                "GET",
                api.appliances_url,
                FakeResponse(401, {"error": "expired token"}),
            ),
        ]

        with patch.object(
            API_MODULE.aiohttp,
            "ClientSession",
            new=FakeClientSessionFactory(requests),
        ):
            with self.assertRaises(API_MODULE.LifeConnectError) as ctx:
                await api.get_appliances_json()

        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(ctx.exception.endpoint, api.appliances_url)
        self.assertFalse(requests)

    async def test_appliances_request_falls_back_to_gateway_after_bapi_failures(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")
        api._access_token = "cached-access-token"
        api._expires = dt.datetime.now() + dt.timedelta(minutes=5)

        requests: list[RequestStep] = [
            (
                "GET",
                api.appliances_url,
                FakeResponse(500, {"error": "backend unavailable"}),
            ),
            (
                "POST",
                api.login_url,
                FakeResponse(
                    200,
                    {"UID": "uid-1", "sessionInfo": {"cookieValue": "login-token"}},
                ),
            ),
            ("POST", api.jwt_url, FakeResponse(200, {"id_token": "jwt-token"})),
            ("POST", api.oauth2_authorize, FakeResponse(200, {"code": "auth-code"})),
            (
                "POST",
                api.oauth2_token,
                FakeResponse(
                    200,
                    {
                        "access_token": "replacement-access-token",
                        "expires_in": 3600,
                        "refresh_token": "replacement-refresh-token",
                    },
                ),
            ),
            (
                "GET",
                api.appliances_url,
                FakeResponse(500, {"error": "backend unavailable"}),
            ),
            (
                "GET",
                API_MODULE.GATEWAY_DEVICE_LIST_URL,
                FakeResponse(200, {"response": {"resultCode": 0, "deviceList": [{"deviceId": "device-1"}]}}),
            ),
        ]

        with patch.object(
            API_MODULE.aiohttp,
            "ClientSession",
            new=FakeClientSessionFactory(requests),
        ):
            result = await api.get_appliances_json()

        self.assertEqual(result, [{"deviceId": "device-1"}])
        self.assertEqual(api._access_token, "replacement-access-token")
        self.assertFalse(requests)

    async def test_appliances_request_falls_back_to_gateway_after_timeout(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")
        api._access_token = "cached-access-token"
        api._expires = dt.datetime.now() + dt.timedelta(minutes=5)

        requests: list[RequestStep] = [
            (
                "GET",
                api.appliances_url,
                TimeoutError(),
            ),
            (
                "GET",
                API_MODULE.GATEWAY_DEVICE_LIST_URL,
                FakeResponse(200, {"response": {"resultCode": 0, "deviceList": [{"deviceId": "device-1"}]}}),
            ),
        ]

        with patch.object(
            API_MODULE.aiohttp,
            "ClientSession",
            new=FakeClientSessionFactory(requests),
        ):
            result = await api.get_appliances_json()

        self.assertEqual(result, [{"deviceId": "device-1"}])
        self.assertFalse(requests)

    async def test_update_appliance_uses_gateway_before_bapi(self) -> None:
        api = ConnectLifeApi("user@example.com", "secret")
        api._access_token = "cached-access-token"
        api._expires = dt.datetime.now() + dt.timedelta(minutes=5)

        requests: list[RequestStep] = [
            (
                "POST",
                API_MODULE.GATEWAY_UPDATE_URL,
                FakeResponse(
                    200,
                    {"response": {"resultCode": 1, "errorCode": 101005, "errorDesc": "randStr check fail."}},
                ),
            ),
            (
                "POST",
                api.appliances_url,
                FakeResponse(200, {"ok": True}),
            ),
        ]

        with patch.object(
            API_MODULE.aiohttp,
            "ClientSession",
            new=FakeClientSessionFactory(requests),
        ):
            await api.update_appliance("puid-1", {"t_temp": "22"})

        self.assertFalse(requests)


if __name__ == "__main__":
    unittest.main()
