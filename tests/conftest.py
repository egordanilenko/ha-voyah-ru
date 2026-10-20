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
from custom_components.voyah.coordinator import VoyahCarInfoCoordinator, VoyahDataUpdateCoordinator

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

MOCK_IMEI = "860000000000001"
MOCK_VIN = "VIN00000000000001"

# Response of GET /car-service/car/v2/{car_id} (car info coordinator data).
MOCK_CAR_INFO_DATA = {
    "_id": MOCK_CAR_ID,
    "vin": MOCK_VIN,
    "imei": MOCK_IMEI,
    "brand": "voyah",
    "carModel": {"name": "Dream", "modname": "H56b"},
    "liveSensors": {"odometer": 251, "soh": 98},
    "updateAvailable": False,
}

# Response of GET /client-bff-service/telemetry/{imei}, captured from the web app (values anonymized).
MOCK_TELEMETRY_RESPONSE = {
    "automations": [],
    "buttons": [
        {"title": "Прогрев", "status": True, "activateCommand": "heatingOn", "deactivateCommand": "heatingOff"},
        {"title": "Охлаждение", "status": False, "activateCommand": "coolingOn", "deactivateCommand": "coolingOff"},
        {
            "title": "Багажник",
            "status": False,
            "activateCommand": "trunkOpen",
            "deactivateCommand": "trunkClose",
            "tag": "trunk",
        },
        {
            "title": "Центральный замок",
            "status": False,
            "activateCommand": "centralLockingOff",
            "deactivateCommand": "centralLockingOn",
            "tag": "central-lock",
        },
        {"title": "Поиск", "status": False, "activateCommand": "search", "deactivateCommand": "search"},
    ],
    "sensors": {
        "12VBatteryVoltage": "14.539999961853027",
        "batteryPercentage": "91",
        "batteryTemp": "",
        "climateFanSpeed": "5",
        "climateTargetTemp": "28",
        "coolantTemp": "2",
        "course": "258",
        "doorFLStatus": False,
        "doorRRStatus": True,
        "fuelPercentage": "100",
        "headLightsStatus": "0",
        "inBoardTemp": "21",
        "isCentralLockingOn": True,
        "isChargingGunInserted": True,
        "isIgnitionOn": True,
        "isParkedOn": True,
        "lat": "55.75",
        "lon": "37.61",
        "odometer": "14348",
        "outsideTemp": "-1.5",
        "remainsBatteryMileage": "113",
        "remainsFuelMileage": "563",
        "signalLevel": "20",
        "tirePressureFL": 2.1,
        "trunkStatus": False,
        "isOnline": True,
    },
    "isOnline": True,
    "onlineState": "connected",
    "firmwareCheck": {"expected": "fw-1.0", "actual": "fw-1.1", "mismatch": True},
    "settingsCheck": {"expected": "cfg-1", "actual": "cfg-1", "mismatch": False},
    "isCarStateReady": True,
    "carStateUpdatedAt": 1792471790719,
    "positionAt": 1792471790709,
    "warnings": [],
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
        "inBoardTemp": 22,
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
        "doorRRStatus": False,
        "isChargingGunInserted": False,
        "isParkedOn": True,
        "isOnline": True,
        "signalLevel": 20,
    },
    "position_data": {
        "lat": 55.7558,
        "lon": 37.6176,
        "course": 90,
        "height": 150,
        "sats": 8,
        "hdop": 1.2,
        "speed": 0,
        "position_at": 1699999990.5,
    },
    "time": 1700000000,
    "last_ping": 6.614,
    "command_states": {
        "heatingOn": True,
        "coolingOn": False,
        "trunkOpen": False,
        "centralLockingOff": False,
        "search": False,
    },
    "checks": {
        "firmwareCheck": {"expected": "fw-1.0", "actual": "fw-1.1", "mismatch": True},
        "settingsCheck": {"expected": "cfg-1", "actual": "cfg-1", "mismatch": False},
    },
}


def make_coordinator(hass: HomeAssistant, data: dict):
    """Create a VoyahDataUpdateCoordinator with pre-set data."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    coordinator = VoyahDataUpdateCoordinator(hass, MagicMock(), entry, update_interval=60)
    coordinator.data = data
    return coordinator


def make_car_info_coordinator(hass: HomeAssistant, data: dict):
    """Create a VoyahCarInfoCoordinator with pre-set data."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    coordinator = VoyahCarInfoCoordinator(hass, MagicMock(), entry)
    coordinator.data = data
    return coordinator


def make_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and register a MockConfigEntry."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)
    return entry
