"""Tests for Voyah button platform."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voyah.api import VoyahApiError
from custom_components.voyah.button import BUTTON_DESCRIPTIONS, VoyahButton, VoyahStartHeatingButton
from custom_components.voyah.const import DOMAIN
from custom_components.voyah.coordinator import VoyahDataUpdateCoordinator

from .conftest import MOCK_CAR_DATA, MOCK_CONFIG_DATA


def _make_coordinator_with_command_client(hass: HomeAssistant) -> tuple[VoyahDataUpdateCoordinator, MockConfigEntry]:
    """Create coordinator with a client that supports TBox commands."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    client = MagicMock()
    client.async_send_command = AsyncMock(return_value={})
    client.async_get_car_data = AsyncMock(return_value=MOCK_CAR_DATA)
    coordinator = VoyahDataUpdateCoordinator(hass, client, entry, update_interval=60)
    coordinator.data = MOCK_CAR_DATA
    return coordinator, entry


async def test_button_press_sends_command(hass: HomeAssistant) -> None:
    """async_press sends the configured command through the coordinator."""
    coordinator, entry = _make_coordinator_with_command_client(hass)
    description = next(d for d in BUTTON_DESCRIPTIONS if d.key == "start_cooling")
    button = VoyahButton(coordinator, description, entry)

    with patch.object(coordinator, "async_send_command", new_callable=AsyncMock) as mock_send:
        await button.async_press()

    mock_send.assert_called_once_with("cooling", "coolingOn")


@pytest.mark.parametrize(
    ("key", "command_states", "expected"),
    [
        ("toggle_central_locking", {"centralLockingOff": False}, ("centralLockingToggle", "centralLockingOff")),
        ("toggle_central_locking", {"centralLockingOff": True}, ("centralLockingToggle", "centralLockingOn")),
        ("toggle_trunk", {"trunkOpen": False}, ("trunkToggle", "trunkOpen")),
        ("toggle_trunk", {"trunkOpen": True}, ("trunkToggle", "trunkClose")),
        ("toggle_trunk", {}, ("trunkToggle", "trunkOpen")),
        ("start_heating", {"heatingOn": True}, ("heating", "heatingOn")),
        ("find_car", {"search": False}, (None, "search")),
    ],
)
async def test_button_press_picks_command_from_state(
    hass: HomeAssistant, key: str, command_states: dict[str, bool], expected: tuple[str, str]
) -> None:
    """Toggles send the activate or deactivate command depending on the reported button state."""
    coordinator, entry = _make_coordinator_with_command_client(hass)
    coordinator.data = {**MOCK_CAR_DATA, "command_states": command_states}
    description = next(d for d in BUTTON_DESCRIPTIONS if d.key == key)
    button = VoyahButton(coordinator, description, entry)

    with patch.object(coordinator, "async_send_command", new_callable=AsyncMock) as mock_send:
        await button.async_press()

    mock_send.assert_called_once_with(*expected)


async def test_button_unique_id(hass: HomeAssistant) -> None:
    """Button unique ID uses car_id."""
    coordinator, entry = _make_coordinator_with_command_client(hass)
    description = next(d for d in BUTTON_DESCRIPTIONS if d.key == "toggle_trunk")
    button = VoyahButton(coordinator, description, entry)
    assert button.unique_id == f"{MOCK_CONFIG_DATA['car_id']}_toggle_trunk"


async def test_start_heating_button_keeps_existing_unique_id(hass: HomeAssistant) -> None:
    """Existing heating button keeps the same unique ID."""
    coordinator, entry = _make_coordinator_with_command_client(hass)
    button = VoyahStartHeatingButton(coordinator, entry)
    assert button.unique_id == f"{MOCK_CONFIG_DATA['car_id']}_start_heating"


async def test_button_press_raises_ha_error_on_api_error(hass: HomeAssistant) -> None:
    """API failures are reported to the user as HomeAssistantError."""
    coordinator, entry = _make_coordinator_with_command_client(hass)
    coordinator.client.async_send_command = AsyncMock(side_effect=VoyahApiError("boom"))
    description = next(d for d in BUTTON_DESCRIPTIONS if d.key == "find_car")
    button = VoyahButton(coordinator, description, entry)

    with pytest.raises(HomeAssistantError):
        await button.async_press()
