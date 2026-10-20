"""Binary sensor platform for the Voyah integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BINARY_SENSOR_DESCRIPTIONS, CHECK_BINARY_SENSOR_DESCRIPTIONS, CONF_CAR_ID, CONF_CAR_NAME, DOMAIN
from .coordinator import VoyahDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voyah binary sensor entities."""
    coordinator: VoyahDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[BinarySensorEntity] = [
        VoyahBinarySensorEntity(coordinator, description, entry)
        for description in BINARY_SENSOR_DESCRIPTIONS
        if description.key in coordinator.data.get("sensors_data", {})
    ]
    entities.extend(
        VoyahCheckBinarySensor(coordinator, description, entry)
        for description in CHECK_BINARY_SENSOR_DESCRIPTIONS
        if description.key in coordinator.data.get("checks", {})
    )
    async_add_entities(entities)


class VoyahBinarySensorEntity(CoordinatorEntity[VoyahDataUpdateCoordinator], BinarySensorEntity):
    """Representation of a Voyah binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VoyahDataUpdateCoordinator,
        description: BinarySensorEntityDescription,
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
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        sensors_data = self.coordinator.data.get("sensors_data", {})
        value = sensors_data.get(self.entity_description.key)
        if value is None:
            return None
        return bool(value)


class VoyahCheckBinarySensor(VoyahBinarySensorEntity):
    """Version check of the new telemetry API: on when the car differs from its profile."""

    @property
    def _check(self) -> dict:
        return self.coordinator.data.get("checks", {}).get(self.entity_description.key) or {}

    @property
    def is_on(self) -> bool | None:
        """Return true if the car version does not match the expected one."""
        mismatch = self._check.get("mismatch")
        if mismatch is None:
            return None
        return bool(mismatch)

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return the version on the car and the version in its profile."""
        return {
            "actual": self._check.get("actual"),
            "expected": self._check.get("expected"),
        }
