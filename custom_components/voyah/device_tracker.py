"""Device tracker platform for the Voyah integration."""

from __future__ import annotations

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CAR_ID, CONF_CAR_NAME, DOMAIN
from .coordinator import VoyahDataUpdateCoordinator

HDOP_TO_METERS = 5.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voyah device tracker."""
    coordinator: VoyahDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    position_data = coordinator.data.get("position_data", {})
    if position_data.get("lat") is not None and position_data.get("lon") is not None:
        async_add_entities([VoyahDeviceTracker(coordinator, entry)])


class VoyahDeviceTracker(
    CoordinatorEntity[VoyahDataUpdateCoordinator], TrackerEntity
):
    """Voyah vehicle GPS tracker."""

    _attr_has_entity_name = True
    _attr_translation_key = "location"

    def __init__(
        self,
        coordinator: VoyahDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        car_id = entry.data.get(CONF_CAR_ID, entry.entry_id)
        self._attr_unique_id = f"{car_id}_location"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, car_id)},
            name=entry.data.get(CONF_CAR_NAME, "Voyah"),
            manufacturer="Voyah",
        )

    @property
    def _position(self) -> dict:
        return self.coordinator.data.get("position_data") or {}

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return self._position.get("lat")

    @property
    def longitude(self) -> float | None:
        return self._position.get("lon")

    @property
    def location_accuracy(self) -> int:
        hdop = self._position.get("hdop")
        if hdop is not None:
            return int(hdop * HDOP_TO_METERS)
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, float | int | None]:
        pos = self._position
        return {
            "course": pos.get("course"),
            "altitude": pos.get("height"),
            "satellites": pos.get("sats"),
            "hdop": pos.get("hdop"),
        }
