"""Button platform for the Voyah integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CAR_ID, CONF_CAR_NAME, DOMAIN
from .coordinator import VoyahDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class VoyahButtonEntityDescription(ButtonEntityDescription):
    """Description of a Voyah button command."""

    # Legacy TBox endpoint: POST /car-service/tbox/{car_id}/{command}; None if the legacy API lacks it
    command: str | None
    # New telemetry API command; for toggles this is the button's activateCommand
    telemetry_command: str
    # Toggles only: deactivateCommand, sent while the API reports the button as active
    telemetry_toggle_command: str | None = None


BUTTON_DESCRIPTIONS: tuple[VoyahButtonEntityDescription, ...] = (
    VoyahButtonEntityDescription(
        key="start_heating",
        translation_key="start_heating",
        icon="mdi:radiator",
        command="heating",
        telemetry_command="heatingOn",
    ),
    VoyahButtonEntityDescription(
        key="start_cooling",
        translation_key="start_cooling",
        icon="mdi:snowflake",
        command="cooling",
        telemetry_command="coolingOn",
    ),
    VoyahButtonEntityDescription(
        key="toggle_central_locking",
        translation_key="toggle_central_locking",
        icon="mdi:car-door-lock",
        command="centralLockingToggle",
        telemetry_command="centralLockingOff",
        telemetry_toggle_command="centralLockingOn",
    ),
    VoyahButtonEntityDescription(
        key="toggle_trunk",
        translation_key="toggle_trunk",
        icon="mdi:car-back",
        command="trunkToggle",
        telemetry_command="trunkOpen",
        telemetry_toggle_command="trunkClose",
    ),
    VoyahButtonEntityDescription(
        key="find_car",
        translation_key="find_car",
        icon="mdi:car-search",
        command=None,
        telemetry_command="search",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voyah button entities."""
    coordinator: VoyahDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    command_states = coordinator.data.get("command_states", {})
    async_add_entities(
        VoyahButton(coordinator, description, entry)
        for description in BUTTON_DESCRIPTIONS
        # Commands missing from the legacy API exist only if the new API lists them.
        if description.command is not None or description.telemetry_command in command_states
    )


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
        await self.coordinator.async_send_command(self.entity_description.command, self._telemetry_command())

    def _telemetry_command(self) -> str:
        """Pick the activate or deactivate command from the button state reported by the API."""
        description = self.entity_description
        command_states = self.coordinator.data.get("command_states", {})
        if description.telemetry_toggle_command and command_states.get(description.telemetry_command):
            return description.telemetry_toggle_command
        return description.telemetry_command


class VoyahStartHeatingButton(VoyahButton):
    """Button to start cabin heating."""

    def __init__(
        self,
        coordinator: VoyahDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, BUTTON_DESCRIPTIONS[0], entry)
