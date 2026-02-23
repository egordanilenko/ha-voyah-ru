"""Config flow for the Voyah integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VoyahApiAuthError, VoyahApiClient, VoyahApiConnectionError, VoyahApiError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CAR_ID,
    CONF_CAR_NAME,
    CONF_PHONE,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class VoyahConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Voyah."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._phone: str = ""
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._organizations: list[dict[str, Any]] = []
        self._cars: list[dict[str, Any]] = []

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Step 1: enter phone number and request SMS."""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = user_input[CONF_PHONE].lstrip("+").replace(" ", "").replace("-", "")
            self._phone = phone

            session = async_get_clientsession(self.hass)
            try:
                await VoyahApiClient.async_request_sms(session, phone)
            except VoyahApiConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception requesting SMS")
                errors["base"] = "unknown"

            if not errors:
                return await self.async_step_code()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_PHONE): str}
            ),
            errors=errors,
        )

    async def async_step_code(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Step 2: enter SMS code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = user_input["code"]
            session = async_get_clientsession(self.hass)

            try:
                auth_data = await VoyahApiClient.async_sign_in(
                    session, self._phone, code
                )
            except VoyahApiAuthError:
                errors["base"] = "invalid_code"
            except (VoyahApiConnectionError, VoyahApiError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during sign-in")
                errors["base"] = "unknown"
            else:
                self._access_token = auth_data["accessToken"]
                self._refresh_token = auth_data["refreshToken"]

                orgs = await VoyahApiClient.async_get_organizations(
                    session, self._access_token
                )
                if len(orgs) > 1:
                    self._organizations = orgs
                    return await self.async_step_organization()

                if len(orgs) == 1:
                    org_id = orgs[0].get("_id", orgs[0].get("id"))
                    try:
                        org_auth = await VoyahApiClient.async_sign_in_org(
                            session, self._access_token, org_id
                        )
                        if "accessToken" in org_auth:
                            self._access_token = org_auth["accessToken"]
                            self._refresh_token = org_auth["refreshToken"]
                    except VoyahApiError:
                        _LOGGER.warning("Org sign-in failed, continuing without org")

                return await self._async_load_cars()

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema(
                {vol.Required("code"): str}
            ),
            errors=errors,
            description_placeholders={"phone": self._phone},
        )

    async def async_step_organization(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Step 3 (optional): select organization."""
        errors: dict[str, str] = {}

        if user_input is not None:
            org_id = user_input["organization"]
            session = async_get_clientsession(self.hass)

            try:
                org_auth = await VoyahApiClient.async_sign_in_org(
                    session, self._access_token, org_id
                )
            except VoyahApiError:
                errors["base"] = "cannot_connect"
            else:
                if "accessToken" in org_auth:
                    self._access_token = org_auth["accessToken"]
                    self._refresh_token = org_auth["refreshToken"]
                return await self._async_load_cars()

        org_options = {
            org.get("_id", org.get("id")): org.get("name", org.get("_id", "?"))
            for org in self._organizations
        }

        return self.async_show_form(
            step_id="organization",
            data_schema=vol.Schema(
                {vol.Required("organization"): vol.In(org_options)}
            ),
            errors=errors,
        )

    async def _async_load_cars(self) -> ConfigFlowResult:
        """Fetch car list and proceed to car selection."""
        session = async_get_clientsession(self.hass)
        self._cars = await VoyahApiClient.async_search_cars(
            session, self._access_token
        )

        if not self._cars:
            return self.async_abort(reason="no_cars")

        if len(self._cars) == 1:
            car = self._cars[0]
            return await self._async_create_entry(car)

        return await self.async_step_car()

    async def async_step_car(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Step 4: select a car."""
        if user_input is not None:
            car_id = user_input["car"]
            car = next(
                (c for c in self._cars if c.get("_id", c.get("id")) == car_id),
                self._cars[0],
            )
            return await self._async_create_entry(car)

        car_options = {
            car.get("_id", car.get("id")): _car_label(car)
            for car in self._cars
        }

        return self.async_show_form(
            step_id="car",
            data_schema=vol.Schema(
                {vol.Required("car"): vol.In(car_options)}
            ),
        )

    async def _async_create_entry(self, car: dict[str, Any]) -> ConfigFlowResult:
        """Create the config entry for a selected car."""
        car_id = car.get("_id", car.get("id"))
        car_name = _car_label(car)

        await self.async_set_unique_id(f"{DOMAIN}_{car_id}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=car_name,
            data={
                CONF_PHONE: self._phone,
                CONF_ACCESS_TOKEN: self._access_token,
                CONF_REFRESH_TOKEN: self._refresh_token,
                CONF_CAR_ID: car_id,
                CONF_CAR_NAME: car_name,
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            },
        )


def _car_label(car: dict[str, Any]) -> str:
    """Human-readable label for a car."""
    parts: list[str] = []
    model = car.get("model") or car.get("modelName")
    name = car.get("name")
    plate = car.get("plateNumber") or car.get("grz")
    vin = car.get("vin")
    if model:
        parts.append(str(model))
    if name and name != model:
        parts.append(str(name))
    if plate:
        parts.append(f"[{plate}]")
    if vin:
        parts.append(f"({vin})")
    return " ".join(parts) if parts else car.get("_id", "Voyah")
