"""Tests for Voyah API client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.voyah.api import VoyahApiAuthError, VoyahApiClient, VoyahApiConnectionError

from .conftest import MOCK_ACCESS_TOKEN, MOCK_CAR_ID, MOCK_REFRESH_TOKEN


def _make_client(session: MagicMock) -> VoyahApiClient:
    return VoyahApiClient(session, MOCK_CAR_ID, MOCK_ACCESS_TOKEN, MOCK_REFRESH_TOKEN)


def _mock_response(status: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


async def test_parse_extracts_fields() -> None:
    """_parse pulls sensorsData, positionData and time."""
    raw = {
        "sensorsData": {"batteryPercentage": 75},
        "positionData": {"lat": 55.0, "lon": 37.0, "speed": 0},
        "time": 1700000000,
    }
    result = VoyahApiClient._parse(raw)
    assert result["sensors_data"]["batteryPercentage"] == 75
    assert result["position_data"]["lat"] == 55.0
    assert result["time"] == 1700000000


async def test_parse_merges_speed_from_position() -> None:
    """Speed from positionData is merged into sensors_data."""
    raw = {
        "sensorsData": {},
        "positionData": {"speed": 60},
        "time": None,
    }
    result = VoyahApiClient._parse(raw)
    assert result["sensors_data"]["speed"] == 60


async def test_get_car_data_success() -> None:
    """async_get_car_data returns parsed data on 200."""
    raw = {
        "sensorsData": {"batteryPercentage": 80},
        "positionData": {},
        "time": 123,
    }
    session = MagicMock()
    session.request = MagicMock(return_value=_mock_response(200, raw))

    client = _make_client(session)
    data = await client.async_get_car_data()
    assert data["sensors_data"]["batteryPercentage"] == 80


async def test_get_car_data_refreshes_token_on_401() -> None:
    """On 401, client refreshes token and retries."""
    raw = {"sensorsData": {"batteryPercentage": 50}, "positionData": {}, "time": 0}
    resp_401 = _mock_response(401, {})
    resp_ok = _mock_response(200, raw)
    refresh_resp = _mock_response(200, {"accessToken": "new-access", "refreshToken": "new-refresh"})

    session = MagicMock()
    session.request = MagicMock(side_effect=[resp_401, resp_ok])
    session.post = MagicMock(return_value=refresh_resp)

    client = _make_client(session)
    data = await client.async_get_car_data()

    assert data["sensors_data"]["batteryPercentage"] == 50
    assert client.access_token == "new-access"


async def test_get_car_data_raises_auth_error_when_refresh_fails() -> None:
    """If refresh fails, VoyahApiAuthError is raised."""
    resp_401 = _mock_response(401, {})
    refresh_resp = _mock_response(401, {})

    session = MagicMock()
    session.request = MagicMock(return_value=resp_401)
    session.post = MagicMock(return_value=refresh_resp)

    client = _make_client(session)
    with pytest.raises(VoyahApiAuthError):
        await client.async_get_car_data()


async def test_request_sms_raises_connection_error_on_5xx() -> None:
    """async_request_sms raises VoyahApiConnectionError on server error."""
    resp = _mock_response(500, {})
    session = MagicMock()
    session.post = MagicMock(return_value=resp)

    with pytest.raises(VoyahApiConnectionError):
        await VoyahApiClient.async_request_sms(session, "79001234567")


async def test_sign_in_raises_auth_error_on_403() -> None:
    """async_sign_in raises VoyahApiAuthError on 403."""
    resp = _mock_response(403, {"message": "Invalid code"})
    session = MagicMock()
    session.post = MagicMock(return_value=resp)

    with pytest.raises(VoyahApiAuthError):
        await VoyahApiClient.async_sign_in(session, "79001234567", "000000")


async def test_sign_in_returns_tokens_on_success() -> None:
    """async_sign_in returns token dict on 200."""
    tokens = {"accessToken": "acc", "refreshToken": "ref"}
    resp = _mock_response(200, tokens)
    session = MagicMock()
    session.post = MagicMock(return_value=resp)

    result = await VoyahApiClient.async_sign_in(session, "79001234567", "123456")
    assert result["accessToken"] == "acc"
