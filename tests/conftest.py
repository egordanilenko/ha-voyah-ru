"""Common fixtures and helpers for Voyah integration tests."""

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voyah.const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_CAR_NAME,
    CONF_PHONE,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.voyah.coordinator import VoyahDataUpdateCoordinator

MOCK_CAR_ID = "car-abc123"
MOCK_PHONE = "79001234567"
MOCK_ACCESS_TOKEN = "access-token-mock"
MOCK_REFRESH_TOKEN = "refresh-token-mock"

MOCK_CONFIG_DATA = {
    CONF_PHONE: MOCK_PHONE,
    CONF_ACCESS_TOKEN: MOCK_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN: MOCK_REFRESH_TOKEN,
    CONF_CAR_ID: MOCK_CAR_ID,
    CONF_CAR_NAME: "Voyah Free",
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
}

MOCK_CAR_DATA = {
    "sensors_data": {
        "batteryPercentage": 80,
        "remainsMileage": 300,
        "fuelPercentage": 50,
        "remainsMileageFuel": 200,
        "12VBatteryVoltage": 12.5,
        "odometer": 15000,
        "outsideTemp": 20,
        "batteryTemp": 25,
        "coolantTemp": 30,
        "climateTargetTemp": 22,
        "climateFanSpeed": 2,
        "tirePressureFL": 2.3,
        "tirePressureFR": 2.3,
        "tirePressureRL": 2.3,
        "tirePressureRR": 2.3,
        "speed": 0,
        "chargingStatus": 0,
        "ignitionStatus": 0,
        "centralLockingStatus": 1,
        "doorFLStatus": 0,
        "doorFRStatus": 0,
        "doorRLStatus": 0,
        "trunkStatus": 0,
        "hatchStatus": 0,
        "climateStatus": 0,
        "securityStatus": 1,
        "headLightsStatus": 0,
        "ready": 1,
        "airingStatus": 0,
        "climateFWindowStatus": 0,
        "mirrorsHeatingStatus": 0,
        "climateWheelHeatingStatus": 0,
        "seatHeatingDriverStatus": 0,
        "seatHeatingFPassStatus": 0,
        "seatHeatingRLPassStatus": 0,
        "seatHeatingRRPassStatus": 0,
    },
    "position_data": {
        "lat": 55.7558,
        "lon": 37.6176,
        "course": 90,
        "alt": 150,
        "sat": 8,
        "hdop": 1.2,
        "speed": 0,
    },
    "time": 1700000000,
}


def make_coordinator(hass: HomeAssistant, data: dict):
    """Create a VoyahDataUpdateCoordinator with pre-set data."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    coordinator = VoyahDataUpdateCoordinator(hass, MagicMock(), entry, update_interval=60)
    coordinator.data = data
    return coordinator


def make_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and register a MockConfigEntry."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    return entry
