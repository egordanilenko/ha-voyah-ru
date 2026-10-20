"""Tests for Voyah data update coordinator."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.voyah.api import VoyahApiAuthError, VoyahApiError
from custom_components.voyah.const import COMMAND_REFRESH_DELAY_SECONDS, DOMAIN
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


async def test_coordinator_persists_tokens_when_update_fails(hass: HomeAssistant) -> None:
    """Tokens refreshed during a failed poll are still saved."""
    client = MagicMock()
    client.access_token = "old-access"
    client.refresh_token = "old-refresh"
    coordinator, entry = _make_coordinator_with_entry(hass, client)
    client.access_token = "new-access"
    client.refresh_token = "new-refresh"
    client.async_get_car_data = AsyncMock(side_effect=VoyahApiError("oops"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert entry.data["refresh_token"] == "new-refresh"


async def test_car_info_coordinator_persists_refreshed_tokens(hass: HomeAssistant) -> None:
    """Tokens refreshed by the car info poll are saved too."""
    client = MagicMock()
    client.access_token = "old-access"
    client.refresh_token = "old-refresh"
    client.async_get_car_info = AsyncMock(return_value=MOCK_CAR_INFO_DATA)
    coordinator, entry = _make_car_info_coordinator_with_entry(hass, client)
    client.access_token = "new-access"
    client.refresh_token = "new-refresh"

    await coordinator._async_update_data()

    assert entry.data["access_token"] == "new-access"
    assert entry.data["refresh_token"] == "new-refresh"


# ── API switch ───────────────────────────────────────────────────────────────


async def test_coordinator_reloads_entry_when_api_changes(hass: HomeAssistant) -> None:
    """When the car moves to another telemetry API, the entry is reloaded to recreate entities."""
    client = MagicMock()
    client.access_token = "token"
    client.refresh_token = "refresh"
    client.uses_telemetry_api = False
    client.async_get_car_data = AsyncMock(return_value=MOCK_CAR_DATA)
    coordinator, entry = _make_coordinator_with_entry(hass, client)

    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as mock_reload:
        await coordinator._async_update_data()
        await coordinator._async_update_data()
        await hass.async_block_till_done()
        mock_reload.assert_not_called()

        client.uses_telemetry_api = True
        await coordinator._async_update_data()
        await hass.async_block_till_done()

    mock_reload.assert_called_once_with(entry.entry_id)


# ── Commands ─────────────────────────────────────────────────────────────────


async def test_send_command_refreshes_after_delays(hass: HomeAssistant) -> None:
    """After a command, data is refreshed once per delay while the car applies it."""
    client = MagicMock()
    client.access_token = "token"
    client.refresh_token = "refresh"
    client.async_send_command = AsyncMock(return_value={"commandId": "cmd-1"})
    coordinator, _ = _make_coordinator_with_entry(hass, client)

    with patch.object(coordinator, "async_request_refresh", new_callable=AsyncMock) as mock_refresh:
        await coordinator.async_send_command("cooling", "coolingOn")
        mock_refresh.assert_not_called()

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=max(COMMAND_REFRESH_DELAY_SECONDS) + 1))
        await hass.async_block_till_done()

    client.async_send_command.assert_called_once_with("cooling", "coolingOn")
    assert mock_refresh.call_count == len(COMMAND_REFRESH_DELAY_SECONDS)


async def test_send_command_raises_ha_error_on_api_error(hass: HomeAssistant) -> None:
    """Command failures reach the user as HomeAssistantError."""
    client = MagicMock()
    client.access_token = "token"
    client.refresh_token = "refresh"
    client.async_send_command = AsyncMock(side_effect=VoyahApiError("boom"))
    coordinator, _ = _make_coordinator_with_entry(hass, client)

    with pytest.raises(HomeAssistantError, match="boom"):
        await coordinator.async_send_command(None, "search")
