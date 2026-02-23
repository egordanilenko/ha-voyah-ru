"""Binary sensor platform for the Voyah integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BINARY_SENSOR_DESCRIPTIONS, CONF_CAR_ID, CONF_CAR_NAME, DOMAIN
from .coordinator import VoyahDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voyah binary sensor entities."""
    coordinator: VoyahDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        VoyahBinarySensorEntity(coordinator, description, entry)
        for description in BINARY_SENSOR_DESCRIPTIONS
        if description.key in coordinator.data.get("sensors_data", {})
    )


class VoyahBinarySensorEntity(
    CoordinatorEntity[VoyahDataUpdateCoordinator], BinarySensorEntity
):
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
