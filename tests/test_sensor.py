"""Tests for Voyah sensor platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.core import HomeAssistant
import time_machine

from custom_components.voyah.const import SENSOR_DESCRIPTIONS
from custom_components.voyah.sensor import RATE_WINDOW_POINTS, VoyahChargingEndTimeSensor, VoyahSensorEntity

from .conftest import MOCK_CAR_DATA, make_config_entry, make_coordinator

# ── VoyahSensorEntity ────────────────────────────────────────────────────────


async def test_sensor_returns_value(hass: HomeAssistant) -> None:
    """Sensor reads value from coordinator data."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "batteryPercentage")
    sensor = VoyahSensorEntity(coordinator, desc, entry)
    assert sensor.native_value == 80


async def test_sensor_returns_none_for_missing_key(hass: HomeAssistant) -> None:
    """Sensor returns None when key absent from data."""
    data = {**MOCK_CAR_DATA, "sensors_data": {}}
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "batteryPercentage")
    sensor = VoyahSensorEntity(coordinator, desc, entry)
    assert sensor.native_value is None


# ── VoyahChargingEndTimeSensor — init ────────────────────────────────────────


async def test_charging_sensor_not_charging_on_init(hass: HomeAssistant) -> None:
    """No end time when not charging at init."""
    data = {
        **MOCK_CAR_DATA,
        "sensors_data": {**MOCK_CAR_DATA["sensors_data"], "chargingStatus": 0},
    }
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)

    assert sensor.native_value is None
    assert sensor._was_charging is False


async def test_charging_sensor_seeds_history_on_init_if_charging(hass: HomeAssistant) -> None:
    """Seeds pct history from first snapshot when already charging."""
    data = {
        **MOCK_CAR_DATA,
        "sensors_data": {**MOCK_CAR_DATA["sensors_data"], "chargingStatus": 1, "batteryPercentage": 60},
        "time": 1000,
    }
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)

    assert sensor._was_charging is True
    assert len(sensor._pct_history) == 1
    assert sensor._pct_history[0] == (60, 1000)


# ── VoyahChargingEndTimeSensor — _compute_end_time ───────────────────────────


async def test_compute_end_time_returns_none_with_one_point(hass: HomeAssistant) -> None:
    """No estimate with only one data point."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    sensor._pct_history.append((50, 1000))

    assert sensor._compute_end_time() is None


async def test_compute_end_time_returns_none_at_100_pct(hass: HomeAssistant) -> None:
    """No estimate when already at 100%."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    sensor._pct_history.append((99, 1000))
    sensor._pct_history.append((100, 2000))

    assert sensor._compute_end_time() is None


async def test_compute_end_time_returns_none_when_rate_zero(hass: HomeAssistant) -> None:
    """No estimate when percentage did not change (rate = 0)."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    sensor._pct_history.append((50, 1000))
    sensor._pct_history.append((50, 2000))  # same pct

    assert sensor._compute_end_time() is None


async def test_compute_end_time_returns_none_when_delta_time_zero(hass: HomeAssistant) -> None:
    """No estimate when timestamps are identical."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    sensor._pct_history.append((50, 1000))
    sensor._pct_history.append((60, 1000))  # same timestamp

    assert sensor._compute_end_time() is None


async def test_compute_end_time_returns_none_when_rate_negative(hass: HomeAssistant) -> None:
    """No estimate when percentage decreased (discharging)."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    sensor._pct_history.append((60, 1000))
    sensor._pct_history.append((55, 2000))  # dropped

    assert sensor._compute_end_time() is None


async def test_compute_end_time_happy_path(hass: HomeAssistant) -> None:
    """Returns the correct future datetime when charging at a steady rate."""
    coordinator = make_coordinator(hass, MOCK_CAR_DATA)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    # 1% per 100 seconds → 40% remaining → exactly 4000 seconds to go
    sensor._pct_history.append((59, 0))
    sensor._pct_history.append((60, 100))

    frozen_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    with time_machine.travel(frozen_now, tick=False):
        result = sensor._compute_end_time()

    assert result == frozen_now + timedelta(seconds=4000)


# ── VoyahChargingEndTimeSensor — _handle_coordinator_update ──────────────────


async def test_update_starts_tracking_when_charging_begins(hass: HomeAssistant) -> None:
    """Tracking starts when chargingStatus transitions 0→1."""
    data = {
        **MOCK_CAR_DATA,
        "sensors_data": {**MOCK_CAR_DATA["sensors_data"], "chargingStatus": 0},
        "time": 1000,
    }
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    assert sensor._was_charging is False

    coordinator.data = {
        **data,
        "sensors_data": {**data["sensors_data"], "chargingStatus": 1, "batteryPercentage": 50},
        "time": 2000,
    }
    with patch.object(sensor, "async_write_ha_state"):
        sensor._handle_coordinator_update()

    assert sensor._was_charging is True
    assert sensor._pct_history[-1] == (50, 2000)


async def test_update_resets_tracking_when_charging_stops(hass: HomeAssistant) -> None:
    """Tracking resets when chargingStatus transitions 1→0."""
    data = {
        **MOCK_CAR_DATA,
        "sensors_data": {**MOCK_CAR_DATA["sensors_data"], "chargingStatus": 1, "batteryPercentage": 70},
        "time": 1000,
    }
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    sensor._was_charging = True
    sensor._pct_history.append((70, 1000))

    coordinator.data = {
        **data,
        "sensors_data": {**data["sensors_data"], "chargingStatus": 0},
    }
    with patch.object(sensor, "async_write_ha_state"):
        sensor._handle_coordinator_update()

    assert sensor._was_charging is False
    assert len(sensor._pct_history) == 0
    assert sensor._cached_end_time is None


async def test_update_adds_point_and_recalculates_on_pct_change(hass: HomeAssistant) -> None:
    """New data point added and end time recalculated when pct changes."""
    data = {
        **MOCK_CAR_DATA,
        "sensors_data": {**MOCK_CAR_DATA["sensors_data"], "chargingStatus": 1, "batteryPercentage": 50},
        "time": 1000,
    }
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    # Clear history seeded by _init_tracking to start fresh
    sensor._pct_history.clear()
    sensor._was_charging = True
    sensor._last_seen_pct = 50
    sensor._pct_history.append((49, 500))
    sensor._pct_history.append((50, 1000))

    coordinator.data = {
        **data,
        "sensors_data": {**data["sensors_data"], "batteryPercentage": 51},
        "time": 2000,
    }
    with patch.object(sensor, "async_write_ha_state"):
        sensor._handle_coordinator_update()

    assert sensor._last_seen_pct == 51
    assert len(sensor._pct_history) == 3
    assert sensor._cached_end_time is not None


async def test_update_skips_recalculation_when_pct_unchanged(hass: HomeAssistant) -> None:
    """No recalculation when battery percentage has not changed."""
    data = {
        **MOCK_CAR_DATA,
        "sensors_data": {**MOCK_CAR_DATA["sensors_data"], "chargingStatus": 1, "batteryPercentage": 50},
        "time": 1000,
    }
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    sensor._was_charging = True
    sensor._last_seen_pct = 50
    sentinel = datetime(2099, 1, 1, tzinfo=timezone.utc)
    sensor._cached_end_time = sentinel

    coordinator.data = {**data, "time": 2000}  # same pct=50
    with patch.object(sensor, "async_write_ha_state"):
        sensor._handle_coordinator_update()

    assert sensor._cached_end_time is sentinel  # untouched


async def test_sliding_window_limited_to_max_points(hass: HomeAssistant) -> None:
    """History never exceeds RATE_WINDOW_POINTS via the update handler."""
    base_sensors = {**MOCK_CAR_DATA["sensors_data"], "chargingStatus": 1}
    data = {**MOCK_CAR_DATA, "sensors_data": base_sensors, "time": 0}
    coordinator = make_coordinator(hass, data)
    entry = make_config_entry(hass)
    sensor = VoyahChargingEndTimeSensor(coordinator, entry)
    sensor._pct_history.clear()
    sensor._was_charging = True

    for i in range(RATE_WINDOW_POINTS + 3):
        pct = 50 + i
        sensor._last_seen_pct = pct - 1  # force "changed" on every update
        coordinator.data = {
            **data,
            "sensors_data": {**base_sensors, "batteryPercentage": pct},
            "time": i * 100,
        }
        with patch.object(sensor, "async_write_ha_state"):
            sensor._handle_coordinator_update()

    assert len(sensor._pct_history) == RATE_WINDOW_POINTS
