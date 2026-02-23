"""API client for the Voyah integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


class VoyahApiError(Exception):
    """Base exception for Voyah API errors."""


class VoyahApiConnectionError(VoyahApiError):
    """Exception for connection errors."""


class VoyahApiAuthError(VoyahApiError):
    """Exception for authentication errors."""


class VoyahApiClient:
    """Client to interact with the Voyah vehicle data API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        car_id: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        self._session = session
        self._car_id = car_id
        self._access_token = access_token
        self._refresh_token = refresh_token

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "x-app": "web",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
    ) -> dict[str, Any]:
        """Send an authenticated request, refreshing the token on 401."""
        url = f"{API_BASE_URL}{path}"
        try:
            async with self._session.request(
                method, url, headers=self._headers(), json=json_data
            ) as resp:
                if resp.status == 401:
                    refreshed = await self._refresh_access_token()
                    if not refreshed:
                        raise VoyahApiAuthError("Authentication failed")
                    async with self._session.request(
                        method, url, headers=self._headers(), json=json_data
                    ) as retry_resp:
                        if retry_resp.status == 401:
                            raise VoyahApiAuthError("Authentication failed")
                        if retry_resp.status != 200:
                            raise VoyahApiError(
                                f"Unexpected status: {retry_resp.status}"
                            )
                        return await retry_resp.json()

                if resp.status != 200:
                    raise VoyahApiError(f"Unexpected status: {resp.status}")
                return await resp.json()

        except aiohttp.ClientError as err:
            raise VoyahApiConnectionError(
                f"Error communicating with API: {err}"
            ) from err

    async def _refresh_access_token(self) -> bool:
        """Use refresh_token to obtain a new access_token pair."""
        url = f"{API_BASE_URL}/id-service/auth/refresh-token"
        try:
            async with self._session.post(
                url,
                headers={"Content-Type": "application/json", "x-app": "web"},
                json={"refreshToken": self._refresh_token},
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Token refresh failed with status %s", resp.status)
                    return False
                data = await resp.json()

            new_access = data.get("accessToken")
            new_refresh = data.get("refreshToken")
            if not new_access or not new_refresh:
                _LOGGER.warning("Token refresh response missing tokens")
                return False

            self._access_token = new_access
            self._refresh_token = new_refresh
            _LOGGER.debug("Access token refreshed successfully")
            return True

        except aiohttp.ClientError as err:
            _LOGGER.warning("Token refresh request failed: %s", err)
            return False

    async def async_get_car_data(self) -> dict[str, Any]:
        """Fetch vehicle data via search endpoint (returns full sensor data)."""
        resp = await self._request(
            "POST",
            "/car-service/car/v2/search",
            json_data={"addSensors": True, "filters": {"_id": self._car_id}},
        )
        rows = resp.get("rows", [])
        if not rows:
            raise VoyahApiError(f"Car {self._car_id} not found in search results")
        raw = rows[0]
        _LOGGER.debug(
            "Car data keys: %s, has sensors: %s",
            list(raw.keys()),
            "sensors" in raw,
        )
        return self._parse(raw)

    @staticmethod
    def _parse(raw: dict[str, Any]) -> dict[str, Any]:
        """Extract relevant fields from the raw API response."""
        sensors = raw.get("sensors") or {}
        sensors_data: dict[str, Any] = sensors.get("sensorsData", {})
        position_data: dict[str, Any] = sensors.get("positionData", {})
        timestamp: int | None = sensors.get("time")

        if position_data.get("speed") is not None:
            sensors_data["speed"] = position_data["speed"]

        _LOGGER.debug(
            "Parsed: %d sensor keys, time=%s",
            len(sensors_data),
            timestamp,
        )
        return {
            "sensors_data": sensors_data,
            "position_data": position_data,
            "time": timestamp,
        }

    # ── Auth helpers (used by config_flow, not during polling) ──

    @staticmethod
    async def async_request_sms(
        session: aiohttp.ClientSession, phone: str
    ) -> None:
        """Request an SMS verification code."""
        url = f"{API_BASE_URL}/id-service/auth/sign-up"
        async with session.post(
            url,
            headers={"Content-Type": "application/json", "x-app": "web"},
            json={"phone": phone, "capchaToken": ""},
        ) as resp:
            if resp.status >= 500:
                raise VoyahApiConnectionError(f"Server error: {resp.status}")

    @staticmethod
    async def async_sign_in(
        session: aiohttp.ClientSession, phone: str, code: str
    ) -> dict[str, Any]:
        """Verify SMS code and return token pair."""
        url = f"{API_BASE_URL}/id-service/auth/sign-in"
        async with session.post(
            url,
            headers={"Content-Type": "application/json", "x-app": "web"},
            json={"phone": phone, "code": code},
        ) as resp:
            data = await resp.json()
            if resp.status == 403:
                raise VoyahApiAuthError(
                    data.get("message", "Invalid code")
                )
            if resp.status != 200:
                raise VoyahApiError(
                    data.get("message", f"Sign-in failed: {resp.status}")
                )
            return data

    @staticmethod
    async def async_get_organizations(
        session: aiohttp.ClientSession, access_token: str
    ) -> list[dict[str, Any]]:
        """Fetch the list of organizations for the authenticated user."""
        url = f"{API_BASE_URL}/id-service/org/my"
        async with session.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-app": "web",
            },
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            if isinstance(data, list):
                return data
            return data.get("rows", data.get("items", []))

    @staticmethod
    async def async_sign_in_org(
        session: aiohttp.ClientSession, access_token: str, org_id: str
    ) -> dict[str, Any]:
        """Select an organization, returning updated tokens."""
        url = f"{API_BASE_URL}/id-service/org/sign-in"
        async with session.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "x-app": "web",
            },
            json={"orgId": org_id},
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise VoyahApiError(
                    data.get("message", f"Org sign-in failed: {resp.status}")
                )
            return data

    @staticmethod
    async def async_search_cars(
        session: aiohttp.ClientSession, access_token: str
    ) -> list[dict[str, Any]]:
        """Fetch available cars for the authenticated user."""
        url = f"{API_BASE_URL}/car-service/car/v2/search"
        async with session.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "x-app": "web",
            },
            json={"addSensors": False},
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("rows", data.get("items", []))
