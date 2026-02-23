"""Sensor platform for the Voyah integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CAR_ID, CONF_CAR_NAME, DOMAIN, SENSOR_DESCRIPTIONS
from .coordinator import VoyahDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voyah sensor entities."""
    coordinator: VoyahDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.debug(
        "Setting up sensors. coordinator.data type=%s, value=%s",
        type(coordinator.data).__name__,
        coordinator.data,
    )

    entities = [
        VoyahSensorEntity(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
        if description.key in coordinator.data.get("sensors_data", {})
    ]
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
