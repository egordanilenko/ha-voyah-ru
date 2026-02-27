"""Button platform for the Voyah integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CAR_ID, CONF_CAR_NAME, DOMAIN
from .coordinator import VoyahDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voyah button entities."""
    coordinator: VoyahDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VoyahStartHeatingButton(coordinator, entry)])


class VoyahStartHeatingButton(
    CoordinatorEntity[VoyahDataUpdateCoordinator], ButtonEntity
):
    """Button to start cabin heating."""

    _attr_has_entity_name = True
    _attr_translation_key = "start_heating"
    _attr_icon = "mdi:radiator"

    def __init__(
        self,
        coordinator: VoyahDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        car_id = entry.data.get(CONF_CAR_ID, entry.entry_id)
        self._attr_unique_id = f"{car_id}_start_heating"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, car_id)},
            name=entry.data.get(CONF_CAR_NAME, "Voyah"),
            manufacturer="Voyah",
        )

    async def async_press(self) -> None:
        """Send the heating command."""
        await self.coordinator.client.async_start_heating()
        await self.coordinator.async_request_refresh()
