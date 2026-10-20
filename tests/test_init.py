"""End-to-end setup tests: HTTP responses → coordinator → entity states."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.voyah.config_flow import VoyahConfigFlow
from custom_components.voyah.const import API_BASE_URL, DOMAIN

from .conftest import MOCK_CAR_ID, MOCK_CAR_INFO_DATA, MOCK_CONFIG_DATA, MOCK_IMEI, MOCK_TELEMETRY_RESPONSE

LEGACY_SENSORS_RESPONSE = {
    "sensorsData": {"batteryPercentage": 80, "centralLockingStatus": 1},
    "positionData": {"lat": 55.0, "lon": 37.0, "speed": 0},
    "time": 1700000000,
    "lastPing": 6.5,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in tests."""
    return


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA, version=VoyahConfigFlow.VERSION)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def _state(hass: HomeAssistant, platform: str, unique_suffix: str) -> State:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{MOCK_CAR_ID}_{unique_suffix}")
    assert entity_id is not None, f"{platform} {unique_suffix} not created"
    state = hass.states.get(entity_id)
    assert state is not None
    return state


async def test_setup_with_new_telemetry_api(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Cars switched to the new telemetry API get their entities from client-bff-service."""
    aioclient_mock.get(f"{API_BASE_URL}/car-service/car/v2/{MOCK_CAR_ID}", json=MOCK_CAR_INFO_DATA)
    aioclient_mock.get(f"{API_BASE_URL}/config-service/config/flags", json={"flags": {"newTelemetryEnabled": True}})
    aioclient_mock.get(f"{API_BASE_URL}/client-bff-service/telemetry/{MOCK_IMEI}", json=MOCK_TELEMETRY_RESPONSE)

    await _setup_entry(hass)

    assert _state(hass, "sensor", "batteryPercentage").state == "91"
    assert _state(hass, "sensor", "remainsMileage").state == "113"
    assert _state(hass, "sensor", "outsideTemp").state == "-1.5"
    assert _state(hass, "sensor", "batteryTemp").state == "unknown"
    assert _state(hass, "sensor", "battery_soh").state == "98"
    assert _state(hass, "binary_sensor", "ignitionStatus").state == "on"
    assert _state(hass, "binary_sensor", "centralLockingStatus").state == "off"
    assert _state(hass, "binary_sensor", "chargingStatus").state == "on"
    assert _state(hass, "binary_sensor", "headLightsStatus").state == "off"
    tracker = _state(hass, "device_tracker", "location")
    assert tracker.attributes["latitude"] == 55.75
    assert tracker.attributes["longitude"] == 37.61
    assert tracker.attributes["position_at"] is not None

    # Entities that exist only for the new telemetry API.
    assert _state(hass, "sensor", "car_status").state == "charging"
    assert _state(hass, "sensor", "signalLevel").state == "20"
    assert _state(hass, "binary_sensor", "doorRRStatus").state == "on"
    assert _state(hass, "binary_sensor", "isChargingGunInserted").state == "on"
    assert _state(hass, "binary_sensor", "isParkedOn").state == "on"
    assert _state(hass, "binary_sensor", "isOnline").state == "on"
    assert _state(hass, "binary_sensor", "firmwareCheck").state == "on"
    assert _state(hass, "binary_sensor", "settingsCheck").state == "off"
    assert _state(hass, "switch", "heating").state == "on"
    assert _state(hass, "switch", "cooling").state == "off"
    assert _state(hass, "button", "find_car") is not None


async def test_setup_with_legacy_tbox_api(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Cars without the rollout flag keep using the legacy TBox sensors endpoint."""
    aioclient_mock.get(f"{API_BASE_URL}/car-service/car/v2/{MOCK_CAR_ID}", json=MOCK_CAR_INFO_DATA)
    aioclient_mock.get(f"{API_BASE_URL}/config-service/config/flags", json={"flags": {"newTelemetryEnabled": False}})
    aioclient_mock.get(f"{API_BASE_URL}/car-service/tbox/{MOCK_CAR_ID}/sensors", json=LEGACY_SENSORS_RESPONSE)

    await _setup_entry(hass)

    assert _state(hass, "sensor", "batteryPercentage").state == "80"
    assert _state(hass, "sensor", "speed").state == "0"
    assert _state(hass, "binary_sensor", "centralLockingStatus").state == "on"
    assert _state(hass, "sensor", "last_ping").state == "6.5"

    registry = er.async_get(hass)
    for platform, suffix in [
        ("sensor", "car_status"),
        ("binary_sensor", "firmwareCheck"),
        ("switch", "heating"),
        ("button", "find_car"),
    ]:
        assert registry.async_get_entity_id(platform, DOMAIN, f"{MOCK_CAR_ID}_{suffix}") is None


async def test_entry_reloads_when_car_moves_to_new_api(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """When the rollout flag turns on at a periodic re-check, entities of the new API appear."""
    aioclient_mock.get(f"{API_BASE_URL}/car-service/car/v2/{MOCK_CAR_ID}", json=MOCK_CAR_INFO_DATA)
    aioclient_mock.get(f"{API_BASE_URL}/config-service/config/flags", json={"flags": {"newTelemetryEnabled": False}})
    aioclient_mock.get(f"{API_BASE_URL}/car-service/tbox/{MOCK_CAR_ID}/sensors", json=LEGACY_SENSORS_RESPONSE)
    with patch("custom_components.voyah.api.time.monotonic", return_value=1000.0):
        entry = await _setup_entry(hass)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("switch", DOMAIN, f"{MOCK_CAR_ID}_heating") is None

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE_URL}/car-service/car/v2/{MOCK_CAR_ID}", json=MOCK_CAR_INFO_DATA)
    aioclient_mock.get(f"{API_BASE_URL}/config-service/config/flags", json={"flags": {"newTelemetryEnabled": True}})
    aioclient_mock.get(f"{API_BASE_URL}/client-bff-service/telemetry/{MOCK_IMEI}", json=MOCK_TELEMETRY_RESPONSE)
    with patch("custom_components.voyah.api.time.monotonic", return_value=1000.0 + 13 * 3600):
        await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_refresh()
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, "switch", "heating").state == "on"
    assert _state(hass, "sensor", "car_status").state == "charging"
