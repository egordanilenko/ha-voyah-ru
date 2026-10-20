"""DataUpdateCoordinator for the Voyah integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VoyahApiAuthError, VoyahApiClient, VoyahApiError
from .const import COMMAND_REFRESH_DELAY_SECONDS, CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)


class VoyahBaseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator sharing the API client; saves tokens the client refreshed."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: VoyahApiClient,
        entry: ConfigEntry,
        name: str,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
        )
        self.client = client
        self._entry = entry
        self._last_access_token = client.access_token
        self._last_refresh_token = client.refresh_token

    def _persist_tokens_if_changed(self) -> None:
        """Save refreshed tokens back to the config entry."""
        new_access = self.client.access_token
        new_refresh = self.client.refresh_token

        if new_access != self._last_access_token or new_refresh != self._last_refresh_token:
            self._last_access_token = new_access
            self._last_refresh_token = new_refresh

            new_data = {**self._entry.data}
            new_data[CONF_ACCESS_TOKEN] = new_access
            new_data[CONF_REFRESH_TOKEN] = new_refresh
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            _LOGGER.debug("Persisted refreshed tokens to config entry")


class VoyahDataUpdateCoordinator(VoyahBaseCoordinator):
    """Coordinator to manage fetching Voyah vehicle data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: VoyahApiClient,
        entry: ConfigEntry,
        update_interval: int,
    ) -> None:
        super().__init__(hass, client, entry, DOMAIN, timedelta(seconds=update_interval))
        self._uses_telemetry_api: bool | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the API."""
        try:
            data = await self.client.async_get_car_data()
        except VoyahApiAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except VoyahApiError as err:
            raise UpdateFailed(f"Error fetching Voyah data: {err}") from err
        finally:
            self._persist_tokens_if_changed()

        self._reload_if_api_changed()
        return data

    def _reload_if_api_changed(self) -> None:
        """Recreate the entities when the car moves between the legacy and the new telemetry API.

        Platforms create entities from the first snapshot, and the two APIs report different sets.
        """
        uses_telemetry_api = self.client.uses_telemetry_api
        if self._uses_telemetry_api is not None and uses_telemetry_api != self._uses_telemetry_api:
            _LOGGER.info("Voyah telemetry API changed, reloading %s to update entities", self._entry.title)
            self.hass.async_create_task(self.hass.config_entries.async_reload(self._entry.entry_id))
        self._uses_telemetry_api = uses_telemetry_api

    async def async_send_command(self, tbox_command: str | None, telemetry_command: str) -> None:
        """Send a remote command, then poll a few times while the car applies it."""
        try:
            await self.client.async_send_command(tbox_command, telemetry_command)
        except VoyahApiError as err:
            raise HomeAssistantError(f"Voyah command failed: {err}") from err
        finally:
            self._persist_tokens_if_changed()

        for delay in COMMAND_REFRESH_DELAY_SECONDS:
            async_call_later(self.hass, delay, self._async_refresh_after_command)

    async def _async_refresh_after_command(self, _now: datetime) -> None:
        await self.async_request_refresh()


CAR_INFO_UPDATE_INTERVAL = timedelta(hours=12)


class VoyahCarInfoCoordinator(VoyahBaseCoordinator):
    """Coordinator for slow-changing car info (SOH, etc.) fetched every 12 hours."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: VoyahApiClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(hass, client, entry, f"{DOMAIN}_car_info", CAR_INFO_UPDATE_INTERVAL)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch car info from the API."""
        try:
            return await self.client.async_get_car_info()
        except VoyahApiAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except VoyahApiError as err:
            raise UpdateFailed(f"Error fetching Voyah car info: {err}") from err
        finally:
            self._persist_tokens_if_changed()
