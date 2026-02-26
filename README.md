# Voyah for Home Assistant

Custom integration for [Home Assistant](https://www.home-assistant.io/) that connects to the [Voyah Assist](https://app.voyahassist.ru) cloud service to monitor Voyah vehicle telemetry.

![Home Assistant screenshot](docs/ha-screenshot.png)

## Features

### Sensors

| Sensor | Unit | Description |
|---|---|---|
| Battery | % | High-voltage battery charge level |
| Remaining range (electric) | km | Estimated range on battery |
| Fuel level | % | Fuel tank level |
| Remaining range (fuel) | km | Estimated range on fuel |
| 12V battery voltage | V | Auxiliary battery voltage |
| Odometer | km | Total mileage |
| Outside temperature | °C | Ambient air temperature |
| Battery temperature | °C | High-voltage battery temperature |
| Coolant temperature | °C | Engine coolant temperature |
| Climate target temperature | °C | Climate control set point |
| Climate fan speed | — | Fan speed level |
| Tire pressure (FL, FR, RL, RR) | bar | Individual tire pressures |
| Speed | km/h | Current vehicle speed |

### Device Tracker

The integration creates a `device_tracker` entity that shows your car's position on the Home Assistant map. GPS coordinates are updated on every polling interval.

| Attribute | Description |
|---|---|
| Latitude / Longitude | Vehicle GPS position (shown on the map) |
| Course | Heading in degrees (0–360) |
| Altitude | Elevation above sea level (meters) |
| Satellites | Number of GPS satellites in use |
| HDOP | Horizontal dilution of precision |
| Location accuracy | Estimated accuracy in meters (derived from HDOP) |

### Binary Sensors

| Sensor | Description |
|---|---|
| Ignition | Engine/ignition state |
| Charging | Charging in progress |
| Central lock | Central locking engaged |
| Doors (FL, FR, RL) | Individual door open/closed |
| Trunk | Trunk open/closed |
| Hatch | Hatch open/closed |
| Climate | Climate control active |
| Security | Security system armed |
| Headlights | Headlights on/off |
| Ready | Vehicle ready state |
| Airing | Ventilation active |
| Climate front window | Front window defrost active |
| Mirrors heating | Mirror heating active |
| Wheel heating | Steering wheel heating active |
| Seat heating (driver, passenger, rear L/R) | Individual seat heating |

### History Charts

| Battery charge | 12V battery voltage | Odometer |
|---|---|---|
| ![Battery](docs/bat-chart.png) | ![12V Battery](docs/12v-bat.png) | ![Odometer](docs/odo-chart.png) |

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Install **Voyah**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/voyah` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Via UI (config flow)

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **Voyah**
3. Enter your phone number (format: `79001234567`)
4. You will receive an SMS with a 4-digit code — enter it
5. If your account has multiple organizations, select one
6. If your account has multiple cars, select one
7. Done — entities will appear automatically

### Manual setup (without config flow)

If the config flow does not work (e.g. the server blocks the SMS request due to captcha), you can set up the integration manually.

#### Step 1: Obtain tokens using the helper script

The repository includes `setup_auth.py` — an interactive script that authenticates you and returns the tokens.

```bash
python3 setup_auth.py
```

The script will:
1. Ask for your phone number
2. Send an SMS code via the Voyah API
3. Ask you to enter the code
4. Authenticate and select the organization/car
5. Print a JSON with `car_id`, `access_token`, and `refresh_token`

#### Step 2: Alternative — obtain tokens from the browser

1. Open https://app.voyahassist.ru in Chrome/Firefox
2. Open DevTools (**F12** or **Cmd+Option+I**)
3. Go to the **Network** tab, enable **Preserve log**
4. Log in with your phone number and SMS code
5. In the Network tab, find the `sign-in` request (or `org/sign-in` if you selected an organization)
6. Open the **Response** tab — copy `accessToken` and `refreshToken`
7. Your `car_id` is visible in any subsequent request URL like `/car-service/car/v2/{car_id}`

#### Step 3: Create config entry manually

Add the following to your `.storage/core.config_entries` file (inside the `entries` array), then restart Home Assistant:

```json
{
    "entry_id": "voyah_manual",
    "version": 2,
    "minor_version": 1,
    "domain": "voyah",
    "title": "Voyah",
    "data": {
        "phone": "79001234567",
        "access_token": "eyJhbGciOi...",
        "refresh_token": "eyJhbGciOi...",
        "car_id": "YOUR_CAR_ID",
        "car_name": "Voyah Free",
        "scan_interval": 60
    },
    "options": {},
    "pref_disable_new_entities": false,
    "pref_disable_polling": false,
    "source": "user",
    "unique_id": "voyah_YOUR_CAR_ID",
    "disabled_by": null
}
```

Replace the values:
- `phone` — your phone number (11 digits, no `+`)
- `access_token` — JWT access token from step 1 or 2
- `refresh_token` — JWT refresh token from step 1 or 2
- `car_id` — your car's ID from the API
- `car_name` — any display name for the device
- `scan_interval` — polling interval in seconds (default: 60)

## Authentication Details

The integration uses the Voyah Assist API at `https://app.voyahassist.ru`.

### Auth flow

| Step | Endpoint | Method |
|---|---|---|
| Request SMS | `/id-service/auth/sign-up` | POST `{phone, capchaToken}` |
| Verify code | `/id-service/auth/sign-in` | POST `{phone, code}` |
| Select org | `/id-service/org/sign-in` | POST `{orgId}` |
| Refresh token | `/id-service/auth/refresh-token` | POST `{refreshToken}` |
| Get car data | `/car-service/car/v2/{carId}` | GET |

### Token lifetimes

| Token | Lifetime | Notes |
|---|---|---|
| Access token | 10 minutes | Refreshed automatically before each request |
| Refresh token | 90 days | New pair issued on every refresh; effectively indefinite |

The integration automatically refreshes the access token when it expires (HTTP 401) and persists the updated tokens to the config entry, so they survive Home Assistant restarts.

If the refresh token itself expires (after 90 days of inactivity), you will need to re-authenticate — either via the config flow or by obtaining new tokens manually.

## Troubleshooting

### "Authentication failed" error

The refresh token has expired. Delete the integration and set it up again.

### SMS code not received

The API may require a valid Yandex SmartCaptcha token. Use the `setup_auth.py` script or obtain tokens from the browser (see Manual setup above).

### Entities show "unavailable"

Check Home Assistant logs for `voyah` — typically means a network error or the API is temporarily down. The integration will retry on the next polling interval.

## License

MIT
