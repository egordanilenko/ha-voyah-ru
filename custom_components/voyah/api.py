"""API client for the Voyah integration."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import time
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import API_BASE_URL, CHARGING_MIN_12V_VOLTAGE

_LOGGER = logging.getLogger(__name__)

FLAGS_PATH = "/config-service/config/flags"
TELEMETRY_PATH = "/client-bff-service/telemetry"
TELEMETRY_COMMANDS_PATH = "/client-bff-service/telemetry-commands"
DEFAULT_BRAND = "voyah"

# Re-check the rollout flag this often, in both directions: a rollout can also be reverted.
TELEMETRY_RECHECK_SECONDS = 12 * 60 * 60
# After a failed check or a failed telemetry poll, check the flag again this soon.
TELEMETRY_RETRY_SECONDS = 5 * 60

# New telemetry key → key used by the legacy API (and by existing entity unique IDs).
TELEMETRY_KEY_ALIASES: dict[str, str] = {
    "remainsBatteryMileage": "remainsMileage",
    "remainsFuelMileage": "remainsMileageFuel",
    "isIgnitionOn": "ignitionStatus",
}

TELEMETRY_POSITION_KEYS = ("lat", "lon", "course")


class VoyahApiError(Exception):
    """Base exception for Voyah API errors."""


class VoyahApiConnectionError(VoyahApiError):
    """Exception for connection errors."""


class VoyahApiAuthError(VoyahApiError):
    """Exception for authentication errors."""


def _coerce_value(value: Any) -> Any:
    """Convert a new-telemetry value (mostly strings) to bool/int/float like the web app does."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    with contextlib.suppress(ValueError):
        return int(text)
    with contextlib.suppress(ValueError):
        return float(text.replace(",", "."))
    return text


def _user_id_from_token(token: str) -> str | None:
    """Read the user id from the access token payload (unverified; used only as a flags hint)."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None
    user_id = claims.get("_id") if isinstance(claims, dict) else None
    return user_id if isinstance(user_id, str) else None


def _as_dict(data: Any, what: str) -> dict[str, Any]:
    """Return a JSON object response, or raise if the API answered with something else."""
    if not isinstance(data, dict):
        raise VoyahApiError(f"Unexpected {what} response: {type(data).__name__}")
    return data


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
        self._refresh_lock = asyncio.Lock()
        # Result of the last successful API check: IMEI for the new telemetry API, None for legacy.
        self._telemetry_imei: str | None = None
        # Monotonic time of the next API check; None until the first one.
        self._api_check_due: float | None = None
        self._api_check_failing = False

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    @property
    def uses_telemetry_api(self) -> bool:
        """Return True while the car is served by the new telemetry API."""
        return self._telemetry_imei is not None

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
        params: dict[str, str] | None = None,
    ) -> Any:
        """Send an authenticated request, refreshing the token on 401."""
        url = f"{API_BASE_URL}{path}"
        try:
            sent_token = self._access_token
            async with self._session.request(
                method, url, headers=self._headers(), json=json_data, params=params
            ) as resp:
                if resp.status != 401:
                    return await self._read_json(resp)

            if not await self._async_refresh_after_401(sent_token):
                raise VoyahApiAuthError("Authentication failed")
            async with self._session.request(
                method, url, headers=self._headers(), json=json_data, params=params
            ) as resp:
                if resp.status == 401:
                    raise VoyahApiAuthError("Authentication failed")
                return await self._read_json(resp)

        except aiohttp.ClientError as err:
            raise VoyahApiConnectionError(f"Error communicating with API: {err}") from err

    @staticmethod
    async def _read_json(resp: aiohttp.ClientResponse) -> Any:
        """Return the decoded body of a successful response ({} for an empty body)."""
        # POST endpoints of the new API answer 201 Created.
        if not 200 <= resp.status < 300:
            raise VoyahApiError(f"Unexpected status: {resp.status}")
        # The backend answers some POSTs with 201, an empty body and no JSON content type.
        text = await resp.text()
        if not text.strip():
            return {}
        try:
            return json.loads(text)
        except ValueError as err:
            raise VoyahApiError(f"Invalid JSON in response: {err}") from err

    async def _async_refresh_after_401(self, rejected_token: str) -> bool:
        """Refresh the token pair once, even if several requests got 401 at the same time."""
        async with self._refresh_lock:
            if self._access_token != rejected_token:
                # Another request refreshed the pair while this one was waiting.
                return True
            return await self._refresh_access_token()

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

        except aiohttp.ClientError as err:
            _LOGGER.warning("Token refresh request failed: %s", err)
            return False
        else:
            new_access = data.get("accessToken")
            new_refresh = data.get("refreshToken")
            if not new_access or not new_refresh:
                _LOGGER.warning("Token refresh response missing tokens")
                return False

            self._access_token = new_access
            self._refresh_token = new_refresh
            _LOGGER.debug("Access token refreshed successfully")
            return True

    async def async_send_command(self, tbox_command: str | None, telemetry_command: str) -> Any:
        """Send a remote command through the API the car is served by.

        ``tbox_command`` is the legacy TBox endpoint name (None if the legacy API
        has no such command), ``telemetry_command`` the command name of the new
        telemetry API.
        """
        imei = await self._async_get_telemetry_imei()
        if imei is None:
            if tbox_command is None:
                raise VoyahApiError(f"Command {telemetry_command} is only available via the new telemetry API")
            return await self.async_send_tbox_command(tbox_command)
        return await self._request(
            "POST",
            TELEMETRY_COMMANDS_PATH,
            json_data={"commandName": telemetry_command, "imei": imei},
        )

    async def async_send_tbox_command(self, command: str) -> Any:
        """Send a command to the car TBox endpoint."""
        return await self._request(
            "POST",
            f"/car-service/tbox/{self._car_id}/{command}",
            json_data={},
        )

    async def async_get_car_info(self) -> dict[str, Any]:
        """Fetch static car info including SOH from car/v2 endpoint."""
        info = await self._request(
            "GET",
            f"/car-service/car/v2/{self._car_id}",
        )
        return _as_dict(info, "car info")

    async def async_get_car_data(self) -> dict[str, Any]:
        """Fetch full telemetry from the API the car is served by."""
        imei = await self._async_get_telemetry_imei()
        if imei is not None:
            try:
                raw = _as_dict(await self._request("GET", f"{TELEMETRY_PATH}/{quote(imei, safe='')}"), "telemetry")
            except VoyahApiAuthError:
                raise
            except VoyahApiError:
                # The rollout may have been reverted for this car: check the flag again soon.
                self._api_check_due = min(self._api_check_due or 0.0, time.monotonic() + TELEMETRY_RETRY_SECONDS)
                raise
            _LOGGER.debug("Telemetry response keys: %s", list(raw.keys()))
            return self._parse_telemetry(raw)

        raw = _as_dict(
            await self._request(
                "GET",
                f"/car-service/tbox/{self._car_id}/sensors",
            ),
            "TBox sensors",
        )
        _LOGGER.debug(
            "Tbox response keys: %s",
            list(raw.keys()),
        )
        return self._parse(raw)

    async def _async_get_telemetry_imei(self) -> str | None:
        """Return the IMEI if the car uses the new telemetry API, None for the legacy TBox API."""
        now = time.monotonic()
        if self._api_check_due is not None and now < self._api_check_due:
            return self._telemetry_imei

        try:
            imei = await self._async_detect_telemetry_imei()
        except VoyahApiAuthError:
            raise
        except VoyahApiError as err:
            # Keep the last known API; before the first successful check that is the legacy one,
            # which is also what the web app falls back to when the flags request fails.
            self._api_check_due = now + TELEMETRY_RETRY_SECONDS
            _LOGGER.log(
                logging.DEBUG if self._api_check_failing else logging.WARNING,
                "Could not check the telemetry API version, keep using the %s API: %s",
                "new telemetry" if self.uses_telemetry_api else "legacy TBox",
                err,
            )
            self._api_check_failing = True
            return self._telemetry_imei

        if self._api_check_due is not None and imei != self._telemetry_imei:
            _LOGGER.info("Car %s switched to the %s API", self._car_id, "new telemetry" if imei else "legacy TBox")
        self._api_check_due = now + TELEMETRY_RECHECK_SECONDS
        self._api_check_failing = False
        self._telemetry_imei = imei
        return imei

    async def _async_detect_telemetry_imei(self) -> str | None:
        """Mirror the web app: the new telemetry API is used when newTelemetryEnabled is set."""
        info = await self.async_get_car_info()
        imei = info.get("imei")
        if isinstance(imei, int) and not isinstance(imei, bool):
            imei = str(imei)
        if not isinstance(imei, str) or not imei:
            _LOGGER.debug("Car %s has no IMEI, using legacy TBox API", self._car_id)
            return None

        car_model = info.get("carModel")
        params = {
            "brand": info.get("brand") or DEFAULT_BRAND,
            "modification": car_model.get("modname") if isinstance(car_model, dict) else None,
            "userId": _user_id_from_token(self._access_token),
            "vin": info.get("vin"),
        }
        flags = _as_dict(
            await self._request(
                "GET",
                FLAGS_PATH,
                params={key: value for key, value in params.items() if isinstance(value, str) and value},
            ),
            "flags",
        )
        flag_values = flags.get("flags")
        enabled = isinstance(flag_values, dict) and bool(flag_values.get("newTelemetryEnabled"))
        _LOGGER.debug("Car %s newTelemetryEnabled=%s", self._car_id, enabled)
        return imei if enabled else None

    @staticmethod
    def _parse(raw: dict[str, Any]) -> dict[str, Any]:
        """Extract relevant fields from the tbox sensors response."""
        payload = raw.get("sensors") if isinstance(raw.get("sensors"), dict) else raw
        sensors = payload.get("sensorsData")
        sensors_data: dict[str, Any] = dict(sensors) if isinstance(sensors, dict) else {}
        position = payload.get("positionData")
        position_data: dict[str, Any] = position if isinstance(position, dict) else {}
        timestamp: int | None = payload.get("time")

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
            "last_ping": payload.get("lastPing"),
        }

    @staticmethod
    def _parse_telemetry(raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize the client-bff telemetry response into the legacy data shape."""
        sensors = raw.get("sensors")
        sensors_data = (
            {key: _coerce_value(value) for key, value in sensors.items()} if isinstance(sensors, dict) else {}
        )
        position_data = {key: sensors_data.pop(key) for key in TELEMETRY_POSITION_KEYS if key in sensors_data}
        position_at = raw.get("positionAt")
        if isinstance(position_at, (int, float)):
            position_data["position_at"] = position_at / 1000

        # The web app takes the online state from the top level, not from sensors.
        if isinstance(raw.get("isOnline"), bool):
            sensors_data["isOnline"] = raw["isOnline"]

        for new_key, legacy_key in TELEMETRY_KEY_ALIASES.items():
            if new_key in sensors_data:
                sensors_data[legacy_key] = sensors_data[new_key]

        # Legacy centralLockingStatus is truthy when unlocked (HA lock sensor: on = unlocked).
        locked = sensors_data.get("isCentralLockingOn")
        if locked is not None:
            sensors_data["centralLockingStatus"] = not locked

        gun_inserted = sensors_data.get("isChargingGunInserted")
        if gun_inserted is not None:
            voltage = sensors_data.get("12VBatteryVoltage")
            if not gun_inserted:
                sensors_data["chargingStatus"] = False
            elif isinstance(voltage, (int, float)):
                sensors_data["chargingStatus"] = voltage >= CHARGING_MIN_12V_VOLTAGE
            else:
                # Without the 12V voltage the charging state cannot be told apart: report it as unknown.
                sensors_data["chargingStatus"] = None

        updated_at = raw.get("carStateUpdatedAt")
        timestamp = updated_at / 1000 if isinstance(updated_at, (int, float)) else None
        # Closest equivalent of the legacy lastPing: seconds since the car last reported its state.
        last_ping = max(time.time() - timestamp, 0.0) if timestamp is not None else None

        command_states: dict[str, bool] = {}
        buttons = raw.get("buttons")
        for button in buttons if isinstance(buttons, list) else []:
            command = button.get("activateCommand") if isinstance(button, dict) else None
            if isinstance(command, str) and command:
                command_states[command] = bool(button.get("status"))

        # firmwareCheck, settingsCheck: {"actual", "expected", "mismatch"}; entities pick the known ones.
        checks = {key: value for key, value in raw.items() if key.endswith("Check") and isinstance(value, dict)}

        _LOGGER.debug(
            "Parsed telemetry: %d sensor keys, time=%s",
            len(sensors_data),
            timestamp,
        )
        return {
            "sensors_data": sensors_data,
            "position_data": position_data,
            "time": timestamp,
            "last_ping": last_ping,
            "command_states": command_states,
            "checks": checks,
        }

    # ── Auth helpers (used by config_flow, not during polling) ──

    @staticmethod
    async def async_request_sms(session: aiohttp.ClientSession, phone: str) -> None:
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
    async def async_sign_in(session: aiohttp.ClientSession, phone: str, code: str) -> dict[str, Any]:
        """Verify SMS code and return token pair."""
        url = f"{API_BASE_URL}/id-service/auth/sign-in"
        async with session.post(
            url,
            headers={"Content-Type": "application/json", "x-app": "web"},
            json={"phone": phone, "code": code},
        ) as resp:
            data = await resp.json()
            if resp.status == 403:
                raise VoyahApiAuthError(data.get("message", "Invalid code"))
            if resp.status != 200:
                raise VoyahApiError(data.get("message", f"Sign-in failed: {resp.status}"))
            return data

    @staticmethod
    async def async_get_organizations(session: aiohttp.ClientSession, access_token: str) -> list[dict[str, Any]]:
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
    async def async_sign_in_org(session: aiohttp.ClientSession, access_token: str, org_id: str) -> dict[str, Any]:
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
                raise VoyahApiError(data.get("message", f"Org sign-in failed: {resp.status}"))
            return data

    @staticmethod
    async def async_search_cars(session: aiohttp.ClientSession, access_token: str) -> list[dict[str, Any]]:
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
