"""Sensor platform for the Voyah integration."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CAR_ID, CONF_CAR_NAME, DOMAIN, SENSOR_DESCRIPTIONS
from .coordinator import VoyahCarInfoCoordinator, VoyahDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

TARGET_BATTERY_PCT = 100
RATE_WINDOW_POINTS = 4  # 4 data points = 3% sliding window


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voyah sensor entities."""
    coordinator: VoyahDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    _LOGGER.debug(
        "Setting up sensors. coordinator.data type=%s, value=%s",
        type(coordinator.data).__name__,
        coordinator.data,
    )

    sensors_data = coordinator.data.get("sensors_data", {})

    entities: list[SensorEntity] = [
        VoyahSensorEntity(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
        if description.key in sensors_data
    ]

    if "batteryPercentage" in sensors_data and "chargingStatus" in sensors_data:
        entities.append(VoyahChargingEndTimeSensor(coordinator, entry))

    car_info_coordinator: VoyahCarInfoCoordinator = hass.data[DOMAIN][entry.entry_id]["car_info_coordinator"]
    car_info = car_info_coordinator.data or {}
    live_sensors = car_info.get("liveSensors") or {}
    if "soh" in live_sensors:
        entities.append(VoyahSohSensor(car_info_coordinator, entry))

    if "last_ping" in coordinator.data:
        entities.append(VoyahLastPingSensor(coordinator, entry))

    _LOGGER.debug("Creating %d sensor entities", len(entities))
    async_add_entities(entities)


class VoyahSensorEntity(CoordinatorEntity[VoyahDataUpdateCoordinator], SensorEntity):
    """Representation of a Voyah sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VoyahDataUpdateCoordinator,
        description: SensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        car_id = entry.data.get(CONF_CAR_ID, entry.entry_id)
        self._attr_unique_id = f"{car_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, car_id)},
            name=entry.data.get(CONF_CAR_NAME, "Voyah"),
            manufacturer="Voyah",
        )

    @property
    def native_value(self) -> float | int | None:
        """Return the sensor value."""
        sensors_data = self.coordinator.data.get("sensors_data", {})
        return sensors_data.get(self.entity_description.key)


class VoyahChargingEndTimeSensor(CoordinatorEntity[VoyahDataUpdateCoordinator], SensorEntity):
    """Estimates charging completion time assuming linear charge rate."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "charging_end_time"
    _attr_icon = "mdi:battery-clock"

    def __init__(
        self,
        coordinator: VoyahDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        car_id = entry.data.get(CONF_CAR_ID, entry.entry_id)
        self._attr_unique_id = f"{car_id}_charging_end_time"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, car_id)},
            name=entry.data.get(CONF_CAR_NAME, "Voyah"),
            manufacturer="Voyah",
        )

        self._pct_history: deque[tuple[float, float]] = deque(maxlen=RATE_WINDOW_POINTS)
        self._last_seen_pct: float | None = None
        self._cached_end_time: datetime | None = None
        self._was_charging: bool = False

        self._init_tracking()

    def _init_tracking(self) -> None:
        """Seed tracking state from the first coordinator snapshot."""
        sensors = self.coordinator.data.get("sensors_data", {})
        if sensors.get("chargingStatus"):
            pct = sensors.get("batteryPercentage")
            api_time = self.coordinator.data.get("time")
            self._was_charging = True
            self._last_seen_pct = pct
            if pct is not None and api_time is not None:
                self._pct_history.append((pct, api_time))
            _LOGGER.debug(
                "Charging already active on init: pct=%s, time=%s",
                pct,
                api_time,
            )

    def _reset_tracking(self) -> None:
        self._pct_history.clear()
        self._last_seen_pct = None
        self._cached_end_time = None
        self._was_charging = False

    def _compute_end_time(self) -> datetime | None:
        """Compute estimated end time from the sliding window."""
        if len(self._pct_history) < 2:
            return None

        oldest_pct, oldest_time = self._pct_history[0]
        newest_pct, newest_time = self._pct_history[-1]

        if newest_pct >= TARGET_BATTERY_PCT:
            return None

        delta_pct = newest_pct - oldest_pct
        delta_time = newest_time - oldest_time

        if delta_pct <= 0 or delta_time <= 0:
            return None

        rate = delta_pct / delta_time  # percent per second
        remaining_pct = TARGET_BATTERY_PCT - newest_pct
        remaining_seconds = remaining_pct / rate
        end_time = datetime.now(tz=timezone.utc) + timedelta(seconds=remaining_seconds)

        _LOGGER.debug(
            "Charge estimate: window=%s pts (%s%%..%s%%), "
            "delta_pct=%s, delta_time=%ss, "
            "rate=%.4f%%/s (%.2f%%/h), remaining_pct=%s, "
            "remaining=%.0fs (%.1fh), end_time=%s",
            len(self._pct_history),
            oldest_pct,
            newest_pct,
            delta_pct,
            delta_time,
            rate,
            rate * 3600,
            remaining_pct,
            remaining_seconds,
            remaining_seconds / 3600,
            end_time.isoformat(),
        )

        return end_time

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recalculate only when charging state or battery percentage changes."""
        sensors = self.coordinator.data.get("sensors_data", {})
        is_charging = bool(sensors.get("chargingStatus"))

        if not is_charging:
            if self._was_charging:
                _LOGGER.debug("Charging stopped, resetting tracking")
                self._reset_tracking()
        elif not self._was_charging:
            pct = sensors.get("batteryPercentage")
            api_time = self.coordinator.data.get("time")
            self._was_charging = True
            self._last_seen_pct = pct
            self._cached_end_time = None
            if pct is not None and api_time is not None:
                self._pct_history.append((pct, api_time))
            _LOGGER.debug("Charging started: pct=%s, time=%s", pct, api_time)
        else:
            current_pct = sensors.get("batteryPercentage")
            if current_pct is not None and current_pct != self._last_seen_pct:
                current_time = self.coordinator.data.get("time")
                _LOGGER.debug(
                    "Battery pct changed: %s -> %s (time=%s)",
                    self._last_seen_pct,
                    current_pct,
                    current_time,
                )
                self._last_seen_pct = current_pct
                if current_time is not None:
                    self._pct_history.append((current_pct, current_time))
                    self._cached_end_time = self._compute_end_time()

        super()._handle_coordinator_update()

    @property
    def native_value(self) -> datetime | None:
        """Return the last computed estimated charging end time."""
        if not self._was_charging:
            return None
        return self._cached_end_time


class VoyahSohSensor(CoordinatorEntity[VoyahCarInfoCoordinator], SensorEntity):
    """State of Health sensor for the high-voltage battery."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery_soh"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-heart"

    def __init__(self, coordinator: VoyahCarInfoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        car_id = entry.data.get(CONF_CAR_ID, entry.entry_id)
        self._attr_unique_id = f"{car_id}_battery_soh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, car_id)},
            name=entry.data.get(CONF_CAR_NAME, "Voyah"),
            manufacturer="Voyah",
        )

    @property
    def native_value(self) -> float | None:
        live = (self.coordinator.data or {}).get("liveSensors") or {}
        return live.get("soh")


class VoyahLastPingSensor(CoordinatorEntity[VoyahDataUpdateCoordinator], SensorEntity):
    """Sensor reporting seconds since the car last connected to the server."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "last_ping"
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self,
        coordinator: VoyahDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        car_id = entry.data.get(CONF_CAR_ID, entry.entry_id)
        self._attr_unique_id = f"{car_id}_last_ping"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, car_id)},
            name=entry.data.get(CONF_CAR_NAME, "Voyah"),
            manufacturer="Voyah",
        )

    @property
    def native_value(self) -> float | None:
        """Return seconds since the last ping from the car."""
        return self.coordinator.data.get("last_ping")
