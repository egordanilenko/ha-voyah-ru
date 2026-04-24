"""Tests for Voyah device tracker platform."""

from homeassistant.components.device_tracker import SourceType
from homeassistant.core import HomeAssistant

from custom_components.voyah.device_tracker import VoyahDeviceTracker

from .conftest import MOCK_CAR_DATA, MOCK_CONFIG_DATA, make_config_entry, make_coordinator


async def test_tracker_returns_lat_lon(hass: HomeAssistant) -> None:
    """latitude and longitude come from position_data."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    tracker = VoyahDeviceTracker(coordinator, entry)

    assert tracker.latitude == 55.7558
    assert tracker.longitude == 37.6176


async def test_tracker_source_type_is_gps(hass: HomeAssistant) -> None:
    """source_type is GPS."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    tracker = VoyahDeviceTracker(coordinator, entry)
    assert tracker.source_type == SourceType.GPS


async def test_tracker_accuracy_computed_from_hdop(hass: HomeAssistant) -> None:
    """location_accuracy = hdop * 5."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    tracker = VoyahDeviceTracker(coordinator, entry)
    # MOCK_CAR_DATA has hdop=1.2 → int(1.2 * 5.0) = 6
    assert tracker.location_accuracy == 6


async def test_tracker_accuracy_zero_when_no_hdop(hass: HomeAssistant) -> None:
    """location_accuracy is 0 when hdop absent."""
    data = {**MOCK_CAR_DATA, "position_data": {"lat": 55.0, "lon": 37.0}}
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    tracker = VoyahDeviceTracker(coordinator, entry)
    assert tracker.location_accuracy == 0


async def test_tracker_extra_state_attributes(hass: HomeAssistant) -> None:
    """Extra attributes include course, altitude, satellites, hdop."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    tracker = VoyahDeviceTracker(coordinator, entry)
    attrs = tracker.extra_state_attributes

    assert attrs["course"] == 90
    assert attrs["hdop"] == 1.2
    assert attrs["altitude"] == 150
    assert attrs["satellites"] == 8


async def test_tracker_returns_none_when_position_missing(hass: HomeAssistant) -> None:
    """lat/lon return None when position_data is empty."""
    data = {**MOCK_CAR_DATA, "position_data": {}}
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    tracker = VoyahDeviceTracker(coordinator, entry)

    assert tracker.latitude is None
    assert tracker.longitude is None


async def test_tracker_unique_id(hass: HomeAssistant) -> None:
    """Unique ID uses car_id + _location."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    tracker = VoyahDeviceTracker(coordinator, entry)
    assert tracker.unique_id == f"{MOCK_CONFIG_DATA['car_id']}_location"
