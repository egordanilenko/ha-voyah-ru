"""Tests for Voyah switch platform."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voyah.api import VoyahApiError
from custom_components.voyah.const import DOMAIN
from custom_components.voyah.coordinator import VoyahDataUpdateCoordinator
from custom_components.voyah.switch import SWITCH_DESCRIPTIONS, VoyahCommandSwitch

from .conftest import MOCK_CAR_DATA, MOCK_CONFIG_DATA


def _make_switch(hass: HomeAssistant, key: str, data: dict = MOCK_CAR_DATA) -> VoyahCommandSwitch:
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    client = MagicMock()
    client.async_send_command = AsyncMock(return_value={"commandId": "cmd-1"})
    coordinator = VoyahDataUpdateCoordinator(hass, client, entry, update_interval=60)
    coordinator.data = data
    description = next(d for d in SWITCH_DESCRIPTIONS if d.key == key)
    return VoyahCommandSwitch(coordinator, description, entry)


async def test_switch_state_from_command_states(hass: HomeAssistant) -> None:
    """Switch state is the button status reported by the telemetry API."""
    assert _make_switch(hass, "heating").is_on is True
    assert _make_switch(hass, "cooling").is_on is False


async def test_switch_state_none_when_missing(hass: HomeAssistant) -> None:
    """Switch state is unknown when the API does not report the command."""
    switch = _make_switch(hass, "heating", {**MOCK_CAR_DATA, "command_states": {}})
    assert switch.is_on is None


@pytest.mark.parametrize(
    ("key", "method", "command"),
    [
        ("heating", "async_turn_on", "heatingOn"),
        ("heating", "async_turn_off", "heatingOff"),
        ("cooling", "async_turn_on", "coolingOn"),
        ("cooling", "async_turn_off", "coolingOff"),
    ],
)
async def test_switch_sends_command(hass: HomeAssistant, key: str, method: str, command: str) -> None:
    """Turning the switch on/off sends the matching command through the coordinator."""
    switch = _make_switch(hass, key)

    with patch.object(switch.coordinator, "async_send_command", new_callable=AsyncMock) as mock_send:
        await getattr(switch, method)()

    mock_send.assert_called_once_with(None, command)


async def test_switch_raises_ha_error_on_api_error(hass: HomeAssistant) -> None:
    """API failures are reported to the user as HomeAssistantError."""
    switch = _make_switch(hass, "heating")
    switch.coordinator.client.async_send_command = AsyncMock(side_effect=VoyahApiError("boom"))

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()


async def test_switch_unique_id(hass: HomeAssistant) -> None:
    """Switch unique ID uses car_id + key."""
    switch = _make_switch(hass, "cooling")
    assert switch.unique_id == f"{MOCK_CONFIG_DATA['car_id']}_cooling"
