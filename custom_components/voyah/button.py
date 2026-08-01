"""Button platform for the Voyah integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CAR_ID, CONF_CAR_NAME, DOMAIN
from .coordinator import VoyahDataUpdateCoordinator

COMMAND_REFRESH_DELAY_SECONDS = (2, 5, 15)


@dataclass(frozen=True, kw_only=True)
class VoyahButtonEntityDescription(ButtonEntityDescription):
    """Description of a Voyah button command."""

    command: str


BUTTON_DESCRIPTIONS: tuple[VoyahButtonEntityDescription, ...] = (
    VoyahButtonEntityDescription(
        key="start_heating",
        translation_key="start_heating",
        icon="mdi:radiator",
        command="heating",
    ),
    VoyahButtonEntityDescription(
        key="start_cooling",
        translation_key="start_cooling",
        icon="mdi:snowflake",
        command="cooling",
    ),
    VoyahButtonEntityDescription(
        key="toggle_central_locking",
        translation_key="toggle_central_locking",
        icon="mdi:car-door-lock",
        command="centralLockingToggle",
    ),
    VoyahButtonEntityDescription(
        key="toggle_trunk",
        translation_key="toggle_trunk",
        icon="mdi:car-back",
        command="trunkToggle",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voyah button entities."""
    coordinator: VoyahDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([VoyahButton(coordinator, description, entry) for description in BUTTON_DESCRIPTIONS])


class VoyahButton(CoordinatorEntity[VoyahDataUpdateCoordinator], ButtonEntity):
    """Button to send a remote vehicle command."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VoyahDataUpdateCoordinator,
        description: VoyahButtonEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.translation_key
        self._attr_icon = description.icon
        car_id = entry.data.get(CONF_CAR_ID, entry.entry_id)
        self._attr_unique_id = f"{car_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, car_id)},
            name=entry.data.get(CONF_CAR_NAME, "Voyah"),
            manufacturer="Voyah",
        )

    async def async_press(self) -> None:
        """Send the configured remote command."""
        await self.coordinator.client.async_send_tbox_command(self.entity_description.command)
        if self.hass is None:
            await self.coordinator.async_request_refresh()
            return

        for delay in COMMAND_REFRESH_DELAY_SECONDS:
            async_call_later(self.hass, delay, self._async_delayed_refresh)

    @callback
    def _async_delayed_refresh(self, _now: datetime) -> None:
        """Request a coordinator refresh after the car has time to apply the command."""
        if self.hass is not None:
            self.hass.async_create_task(self.coordinator.async_request_refresh())


class VoyahStartHeatingButton(VoyahButton):
    """Button to start cabin heating."""

    def __init__(
        self,
        coordinator: VoyahDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, BUTTON_DESCRIPTIONS[0], entry)
