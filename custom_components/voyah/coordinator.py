"""DataUpdateCoordinator for the Voyah integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VoyahApiAuthError, VoyahApiClient, VoyahApiError
from .const import CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

type VoyahConfigEntry = ConfigEntry[VoyahDataUpdateCoordinator]


class VoyahDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching Voyah vehicle data."""

    config_entry: VoyahConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: VoyahApiClient,
        entry: ConfigEntry,
        update_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self._entry = entry
        self._last_access_token = client.access_token
        self._last_refresh_token = client.refresh_token

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the API."""
        try:
            data = await self.client.async_get_car_data()
        except VoyahApiAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except VoyahApiError as err:
            raise UpdateFailed(f"Error fetching Voyah data: {err}") from err

        self._persist_tokens_if_changed()
        return data

    def _persist_tokens_if_changed(self) -> None:
        """Save refreshed tokens back to the config entry."""
        new_access = self.client.access_token
        new_refresh = self.client.refresh_token

        if (
            new_access != self._last_access_token
            or new_refresh != self._last_refresh_token
        ):
            self._last_access_token = new_access
            self._last_refresh_token = new_refresh

            new_data = {**self._entry.data}
            new_data[CONF_ACCESS_TOKEN] = new_access
            new_data[CONF_REFRESH_TOKEN] = new_refresh
            self.hass.config_entries.async_update_entry(
                self._entry, data=new_data
            )
            _LOGGER.debug("Persisted refreshed tokens to config entry")
