"""Tests for Voyah data update coordinator."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voyah.api import VoyahApiAuthError, VoyahApiError
from custom_components.voyah.const import DOMAIN
from custom_components.voyah.coordinator import VoyahCarInfoCoordinator, VoyahDataUpdateCoordinator

from .conftest import MOCK_CAR_DATA, MOCK_CAR_INFO_DATA, MOCK_CONFIG_DATA


def _make_coordinator_with_entry(
    hass: HomeAssistant, client: MagicMock
) -> tuple[VoyahDataUpdateCoordinator, MockConfigEntry]:
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    coordinator = VoyahDataUpdateCoordinator(hass, client, entry, update_interval=60)
    coordinator.config_entry = entry
    return coordinator, entry


async def test_coordinator_fetches_data(hass: HomeAssistant) -> None:
    """Coordinator returns data from API on success."""
    client = MagicMock()
    client.access_token = "token"
    client.refresh_token = "refresh"
    client.async_get_car_data = AsyncMock(return_value=MOCK_CAR_DATA)

    coordinator, _ = _make_coordinator_with_entry(hass, client)
    data = await coordinator._async_update_data()

    assert data["sensors_data"]["batteryPercentage"] == 80
    assert data["position_data"]["lat"] == 55.7558


async def test_coordinator_raises_update_failed_on_api_error(hass: HomeAssistant) -> None:
    """API error raises UpdateFailed."""
    client = MagicMock()
    client.access_token = "token"
    client.refresh_token = "refresh"
    client.async_get_car_data = AsyncMock(side_effect=VoyahApiError("oops"))

    coordinator, _ = _make_coordinator_with_entry(hass, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_raises_auth_failed_on_auth_error(hass: HomeAssistant) -> None:
    """Auth error raises ConfigEntryAuthFailed."""
    client = MagicMock()
    client.access_token = "token"
    client.refresh_token = "refresh"
    client.async_get_car_data = AsyncMock(side_effect=VoyahApiAuthError("expired"))

    coordinator, _ = _make_coordinator_with_entry(hass, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


def _make_car_info_coordinator_with_entry(
    hass: HomeAssistant, client: MagicMock
) -> tuple[VoyahCarInfoCoordinator, MockConfigEntry]:
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    coordinator = VoyahCarInfoCoordinator(hass, client, entry)
    coordinator.config_entry = entry
    return coordinator, entry


async def test_car_info_coordinator_fetches_data(hass: HomeAssistant) -> None:
    """VoyahCarInfoCoordinator returns car info data from API on success."""
    client = MagicMock()
    client.async_get_car_info = AsyncMock(return_value=MOCK_CAR_INFO_DATA)

    coordinator, _ = _make_car_info_coordinator_with_entry(hass, client)
    data = await coordinator._async_update_data()

    assert data["liveSensors"]["soh"] == 98


async def test_car_info_coordinator_raises_update_failed_on_api_error(hass: HomeAssistant) -> None:
    """VoyahApiError raises UpdateFailed in VoyahCarInfoCoordinator."""
    client = MagicMock()
    client.async_get_car_info = AsyncMock(side_effect=VoyahApiError("api error"))

    coordinator, _ = _make_car_info_coordinator_with_entry(hass, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_car_info_coordinator_raises_auth_failed_on_auth_error(hass: HomeAssistant) -> None:
    """VoyahApiAuthError raises ConfigEntryAuthFailed in VoyahCarInfoCoordinator."""
    client = MagicMock()
    client.async_get_car_info = AsyncMock(side_effect=VoyahApiAuthError("auth error"))

    coordinator, _ = _make_car_info_coordinator_with_entry(hass, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_persists_refreshed_tokens(hass: HomeAssistant) -> None:
    """Coordinator saves new tokens to config entry when they change."""
    client = MagicMock()
    client.access_token = "new-access"
    client.refresh_token = "new-refresh"
    client.async_get_car_data = AsyncMock(return_value=MOCK_CAR_DATA)

    coordinator, entry = _make_coordinator_with_entry(hass, client)
    # _last_* were set from original tokens, now client has new ones
    coordinator._last_access_token = "old-access"
    coordinator._last_refresh_token = "old-refresh"

    await coordinator._async_update_data()

    assert entry.data["access_token"] == "new-access"
    assert entry.data["refresh_token"] == "new-refresh"
