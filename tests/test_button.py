"""Tests for Voyah button platform."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voyah.button import VoyahStartHeatingButton
from custom_components.voyah.const import DOMAIN
from custom_components.voyah.coordinator import VoyahDataUpdateCoordinator

from .conftest import MOCK_CAR_DATA, MOCK_CONFIG_DATA


def _make_coordinator_with_heating_client(hass):
    """Create coordinator with a client that supports async_start_heating."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    client = MagicMock()
    client.async_start_heating = AsyncMock(return_value={})
    client.async_get_car_data = AsyncMock(return_value=MOCK_CAR_DATA)
    coordinator = VoyahDataUpdateCoordinator(hass, client, entry, update_interval=60)
    coordinator.data = MOCK_CAR_DATA
    return coordinator, entry


async def test_button_press_calls_heating_and_refreshes(hass: HomeAssistant) -> None:
    """async_press sends heating command and triggers coordinator refresh."""
    coordinator, entry = _make_coordinator_with_heating_client(hass)
    button = VoyahStartHeatingButton(coordinator, entry)

    with patch.object(coordinator, "async_request_refresh", new_callable=AsyncMock) as mock_refresh:
        await button.async_press()

    coordinator.client.async_start_heating.assert_called_once()
    mock_refresh.assert_called_once()


async def test_button_unique_id(hass: HomeAssistant) -> None:
    """Button unique ID uses car_id."""
    coordinator, entry = _make_coordinator_with_heating_client(hass)
    button = VoyahStartHeatingButton(coordinator, entry)
    assert button.unique_id == f"{MOCK_CONFIG_DATA['car_id']}_start_heating"
