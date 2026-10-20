"""Tests for Voyah binary sensor platform."""

from homeassistant.core import HomeAssistant
import pytest

from custom_components.voyah.binary_sensor import VoyahBinarySensorEntity, VoyahCheckBinarySensor
from custom_components.voyah.const import BINARY_SENSOR_DESCRIPTIONS, CHECK_BINARY_SENSOR_DESCRIPTIONS

from .conftest import MOCK_CAR_DATA, MOCK_CONFIG_DATA, make_config_entry, make_coordinator


async def test_binary_sensor_is_on_when_value_truthy(hass: HomeAssistant) -> None:
    """is_on returns True for non-zero value."""
    data = {**MOCK_CAR_DATA, "sensors_data": {"ignitionStatus": 1}}
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "ignitionStatus")
    sensor = VoyahBinarySensorEntity(coordinator, desc, entry)
    assert sensor.is_on is True


async def test_binary_sensor_is_off_when_value_zero(hass: HomeAssistant) -> None:
    """is_on returns False for zero value."""
    data = {**MOCK_CAR_DATA, "sensors_data": {"ignitionStatus": 0}}
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "ignitionStatus")
    sensor = VoyahBinarySensorEntity(coordinator, desc, entry)
    assert sensor.is_on is False


async def test_binary_sensor_returns_none_for_missing_key(hass: HomeAssistant) -> None:
    """is_on returns None when key absent."""
    data = {**MOCK_CAR_DATA, "sensors_data": {}}
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "chargingStatus")
    sensor = VoyahBinarySensorEntity(coordinator, desc, entry)
    assert sensor.is_on is None


async def test_binary_sensor_unique_id(hass: HomeAssistant) -> None:
    """Unique ID uses car_id + key."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "ignitionStatus")
    sensor = VoyahBinarySensorEntity(coordinator, desc, entry)
    assert sensor.unique_id == f"{MOCK_CONFIG_DATA['car_id']}_ignitionStatus"


@pytest.mark.parametrize("key", ["doorRRStatus", "isChargingGunInserted", "isParkedOn", "isOnline"])
async def test_new_telemetry_binary_sensors_read_values(hass: HomeAssistant, key: str) -> None:
    """Binary sensors added for the new telemetry API read their keys."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == key)
    sensor = VoyahBinarySensorEntity(coordinator, desc, entry)
    assert sensor.is_on is bool(MOCK_CAR_DATA["sensors_data"][key])


# ── VoyahCheckBinarySensor ───────────────────────────────────────────────────


async def test_check_sensor_reports_mismatch_with_versions(hass: HomeAssistant) -> None:
    """Firmware check is on when versions mismatch and exposes both versions."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    desc = next(d for d in CHECK_BINARY_SENSOR_DESCRIPTIONS if d.key == "firmwareCheck")
    sensor = VoyahCheckBinarySensor(coordinator, desc, entry)

    assert sensor.is_on is True
    assert sensor.extra_state_attributes == {"actual": "fw-1.1", "expected": "fw-1.0"}
    assert sensor.unique_id == f"{MOCK_CONFIG_DATA['car_id']}_firmwareCheck"


async def test_check_sensor_off_when_versions_match(hass: HomeAssistant) -> None:
    """Settings check is off when the car matches its profile."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    desc = next(d for d in CHECK_BINARY_SENSOR_DESCRIPTIONS if d.key == "settingsCheck")
    sensor = VoyahCheckBinarySensor(coordinator, desc, entry)
    assert sensor.is_on is False


async def test_check_sensor_none_when_missing(hass: HomeAssistant) -> None:
    """Check sensor is unknown when the API omits the check."""
    data = {**MOCK_CAR_DATA, "checks": {}}
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    desc = next(d for d in CHECK_BINARY_SENSOR_DESCRIPTIONS if d.key == "firmwareCheck")
    sensor = VoyahCheckBinarySensor(coordinator, desc, entry)

    assert sensor.is_on is None
    assert sensor.extra_state_attributes == {"actual": None, "expected": None}
