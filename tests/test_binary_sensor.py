"""Tests for Voyah binary sensor platform."""

from homeassistant.core import HomeAssistant

from custom_components.voyah.binary_sensor import VoyahBinarySensorEntity
from custom_components.voyah.const import BINARY_SENSOR_DESCRIPTIONS

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
