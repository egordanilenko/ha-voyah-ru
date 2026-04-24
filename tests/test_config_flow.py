"""Tests for Voyah config flow."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voyah.api import VoyahApiAuthError, VoyahApiConnectionError
from custom_components.voyah.config_flow import _car_label
from custom_components.voyah.const import DOMAIN

from .conftest import MOCK_ACCESS_TOKEN, MOCK_CAR_ID, MOCK_CONFIG_DATA, MOCK_PHONE, MOCK_REFRESH_TOKEN

MOCK_AUTH_RESPONSE = {
    "accessToken": MOCK_ACCESS_TOKEN,
    "refreshToken": MOCK_REFRESH_TOKEN,
}
MOCK_CARS = [{"_id": MOCK_CAR_ID, "model": "Free", "vin": "VIN123"}]
MOCK_ORGS = [{"_id": "org-1", "name": "My Org"}]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in tests."""
    return


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Initial step shows the phone number form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_connection_error(hass: HomeAssistant) -> None:
    """Connection error on SMS request shows cannot_connect."""
    with patch(
        "custom_components.voyah.config_flow.VoyahApiClient.async_request_sms",
        side_effect=VoyahApiConnectionError,
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": MOCK_PHONE})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_full_flow_single_org_single_car(hass: HomeAssistant) -> None:
    """Happy path: single org + single car creates entry without extra steps."""
    with (
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_request_sms",
            return_value=None,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_sign_in",
            return_value=MOCK_AUTH_RESPONSE,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_get_organizations",
            return_value=MOCK_ORGS,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_sign_in_org",
            return_value=MOCK_AUTH_RESPONSE,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_search_cars",
            return_value=MOCK_CARS,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": MOCK_PHONE})
        assert result["step_id"] == "code"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "123456"})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["car_id"] == MOCK_CAR_ID
    assert result["data"]["phone"] == MOCK_PHONE


async def test_code_step_invalid_code(hass: HomeAssistant) -> None:
    """Invalid SMS code shows invalid_code error."""
    with patch(
        "custom_components.voyah.config_flow.VoyahApiClient.async_request_sms",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": MOCK_PHONE})

    with patch(
        "custom_components.voyah.config_flow.VoyahApiClient.async_sign_in",
        side_effect=VoyahApiAuthError,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "000000"})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "code"
    assert result["errors"]["base"] == "invalid_code"


async def test_multiple_cars_shows_car_step(hass: HomeAssistant) -> None:
    """Multiple cars result in the car selection step."""
    cars = [
        {"_id": "car-1", "model": "Free"},
        {"_id": "car-2", "model": "Dream"},
    ]
    with (
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_request_sms",
            return_value=None,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_sign_in",
            return_value=MOCK_AUTH_RESPONSE,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_get_organizations",
            return_value=MOCK_ORGS,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_sign_in_org",
            return_value=MOCK_AUTH_RESPONSE,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_search_cars",
            return_value=cars,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": MOCK_PHONE})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "123456"})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "car"


async def test_no_cars_aborts(hass: HomeAssistant) -> None:
    """No cars found aborts the flow."""
    with (
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_request_sms",
            return_value=None,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_sign_in",
            return_value=MOCK_AUTH_RESPONSE,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_get_organizations",
            return_value=MOCK_ORGS,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_sign_in_org",
            return_value=MOCK_AUTH_RESPONSE,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_search_cars",
            return_value=[],
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": MOCK_PHONE})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "123456"})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_cars"


async def test_duplicate_entry_aborts(hass: HomeAssistant) -> None:
    """Second setup for the same car aborts with already_configured."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{DOMAIN}_{MOCK_CAR_ID}",
        data=MOCK_CONFIG_DATA,
    )
    existing.add_to_hass(hass)

    with (
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_request_sms",
            return_value=None,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_sign_in",
            return_value=MOCK_AUTH_RESPONSE,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_get_organizations",
            return_value=MOCK_ORGS,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_sign_in_org",
            return_value=MOCK_AUTH_RESPONSE,
        ),
        patch(
            "custom_components.voyah.config_flow.VoyahApiClient.async_search_cars",
            return_value=MOCK_CARS,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": MOCK_PHONE})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "123456"})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def test_car_label_uses_car_model_display_name() -> None:
    """_car_label reads model name from carModel.displayName."""
    car = {
        "_id": "aabbccddeeff001122334455",
        "vin": "TEST0000000000001",
        "carModel": {
            "name": "Dream",
            "displayName": "МЕЧТА / DREAM",
        },
    }
    label = _car_label(car)
    assert "МЕЧТА / DREAM" in label
    assert "TEST0000000000001" in label


def test_car_label_falls_back_to_car_model_name() -> None:
    """_car_label falls back to carModel.name when displayName is absent."""
    car = {
        "_id": "abc123",
        "vin": "VIN000",
        "carModel": {"name": "Free"},
    }
    label = _car_label(car)
    assert "Free" in label


def test_car_label_falls_back_to_top_level_model() -> None:
    """_car_label falls back to top-level model/modelName keys for old API format."""
    car = {"_id": "abc123", "vin": "VIN000", "model": "Free"}
    label = _car_label(car)
    assert "Free" in label


def test_car_label_only_vin_when_no_model() -> None:
    """_car_label shows only VIN when no model info is present."""
    car = {"_id": "abc123", "vin": "TEST0000000000002"}
    label = _car_label(car)
    assert label == "(TEST0000000000002)"
