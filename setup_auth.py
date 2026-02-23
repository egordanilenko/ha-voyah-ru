#!/usr/bin/env python3
"""Interactive script to obtain Voyah API credentials.

Performs SMS-based authentication against app.voyahassist.ru,
lets you pick an organization and a car, then prints the
accessToken, refreshToken and car ID needed for the HA integration.

No external dependencies — uses only the Python standard library.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request

BASE_URL = "https://app.voyahassist.ru"
HEADERS_BASE = {
    "Content-Type": "application/json",
    "x-app": "web",
}

# Disable certificate verification only if the system bundle is missing.
# In normal environments this is not needed.
_SSL_CTX: ssl.SSLContext | None = None


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    """Send an HTTP request and return (status_code, parsed_json)."""
    url = f"{BASE_URL}{path}"
    headers = dict(HEADERS_BASE)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        resp = urllib.request.urlopen(req, context=_SSL_CTX)
        raw = resp.read().decode()
        return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode()
            payload = json.loads(raw) if raw.strip() else {"message": exc.reason}
        except Exception:
            payload = {"message": exc.reason}
        return exc.code, payload


def request_sms(phone: str) -> None:
    """Step 1: request an SMS code for the given phone number."""
    status, data = _request(
        "POST",
        "/id-service/auth/sign-up",
        body={"phone": phone, "capchaToken": ""},
    )
    if status >= 400:
        msg = data.get("message", "Unknown error")
        print(f"\n  [!] SMS request failed ({status}): {msg}")
        if "captcha" in msg.lower() or "капча" in msg.lower():
            print("      The server requires a valid captcha token.")
            print("      You may need to obtain tokens manually via the browser.")
            sys.exit(1)
        if status == 400:
            print("      The server returned an error, but the SMS may still have been sent.")
            print("      Check your phone — if you received a code, continue.\n")
            return
        sys.exit(1)

    print("\n  [OK] SMS code sent successfully.\n")


def sign_in(phone: str, code: str) -> dict:
    """Step 2: verify SMS code and obtain tokens."""
    status, data = _request(
        "POST",
        "/id-service/auth/sign-in",
        body={"phone": phone, "code": code},
    )
    if status >= 400:
        msg = data.get("message", "Unknown error")
        print(f"\n  [!] Sign-in failed ({status}): {msg}")
        sys.exit(1)

    if "accessToken" not in data:
        print(f"\n  [!] Unexpected sign-in response: {json.dumps(data, indent=2)}")
        sys.exit(1)

    return data


def get_organizations(token: str) -> list[dict]:
    """Fetch the list of organizations the user belongs to."""
    status, data = _request("GET", "/id-service/org/my", token=token)
    if status >= 400:
        return []
    if isinstance(data, list):
        return data
    return data.get("rows", data.get("items", [data] if "_id" in data else []))


def sign_in_org(org_id: str, token: str) -> dict:
    """Select an organization and obtain org-scoped tokens."""
    status, data = _request(
        "POST",
        "/id-service/org/sign-in",
        body={"orgId": org_id},
        token=token,
    )
    if status >= 400:
        msg = data.get("message", "Unknown error")
        print(f"\n  [!] Org sign-in failed ({status}): {msg}")
        sys.exit(1)
    return data


def search_cars(token: str) -> list[dict]:
    """Fetch the list of cars available to the user."""
    status, data = _request(
        "POST",
        "/car-service/car/v2/search",
        body={"addSensors": False},
        token=token,
    )
    if status >= 400:
        msg = data.get("message", "Unknown error")
        print(f"\n  [!] Car search failed ({status}): {msg}")
        return []
    return data.get("rows", data.get("items", []))


def pick_option(items: list[dict], label_fn, id_fn, entity_name: str) -> dict:
    """Interactive picker for a list of items."""
    if not items:
        print(f"\n  No {entity_name}s found.")
        sys.exit(1)

    if len(items) == 1:
        chosen = items[0]
        print(f"\n  Auto-selected the only {entity_name}: {label_fn(chosen)}")
        return chosen

    print(f"\n  Available {entity_name}s:")
    for i, item in enumerate(items, 1):
        print(f"    {i}. {label_fn(item)}")

    while True:
        raw = input(f"\n  Select {entity_name} [1-{len(items)}]: ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(items):
                return items[idx]
        except ValueError:
            pass
        print("  Invalid choice, try again.")


def car_label(car: dict) -> str:
    """Human-readable label for a car."""
    parts = []
    vin = car.get("vin")
    model = car.get("model") or car.get("modelName")
    plate = car.get("plateNumber") or car.get("grz")
    name = car.get("name")
    if model:
        parts.append(model)
    if name and name != model:
        parts.append(name)
    if plate:
        parts.append(f"[{plate}]")
    if vin:
        parts.append(f"(VIN: {vin})")
    car_id = car.get("_id", car.get("id", ""))
    if not parts:
        parts.append(car_id)
    return " ".join(parts)


def main() -> None:
    print("=" * 60)
    print("  Voyah API — Authentication Helper")
    print("=" * 60)

    # --- Phone ---
    phone = input("\n  Phone number (e.g. 79001234567): ").strip()
    phone = phone.lstrip("+").replace(" ", "").replace("-", "")
    if not phone.isdigit() or len(phone) != 11:
        print("  [!] Phone must be 11 digits (e.g. 79001234567)")
        sys.exit(1)

    print(f"\n  Requesting SMS code for {phone}...")
    request_sms(phone)

    # --- SMS code ---
    code = input("  Enter the 4-digit SMS code: ").strip()
    if not code.isdigit() or len(code) != 4:
        print("  [!] Code must be exactly 4 digits")
        sys.exit(1)

    print("  Signing in...")
    auth = sign_in(phone, code)
    access_token = auth["accessToken"]
    refresh_token = auth["refreshToken"]
    print("  [OK] Authenticated!\n")

    # --- Organization ---
    print("  Fetching organizations...")
    orgs = get_organizations(access_token)
    if orgs:
        org = pick_option(
            orgs,
            label_fn=lambda o: o.get("name", o.get("_id", "?")),
            id_fn=lambda o: o.get("_id", o.get("id")),
            entity_name="organization",
        )
        org_id = org.get("_id", org.get("id"))
        print(f"  Signing into organization {org_id}...")
        org_auth = sign_in_org(org_id, access_token)
        if "accessToken" in org_auth:
            access_token = org_auth["accessToken"]
            refresh_token = org_auth["refreshToken"]
            print("  [OK] Organization selected, tokens updated.\n")
    else:
        print("  No organizations found (or single-org account), skipping.\n")

    # --- Cars ---
    print("  Fetching cars...")
    cars = search_cars(access_token)
    car = pick_option(
        cars,
        label_fn=car_label,
        id_fn=lambda c: c.get("_id", c.get("id")),
        entity_name="car",
    )
    car_id = car.get("_id", car.get("id"))

    # --- Result ---
    print("\n" + "=" * 60)
    print("  RESULT — save these values for the HA integration")
    print("=" * 60)
    print(f"\n  car_id:        {car_id}")
    print(f"  accessToken:   {access_token[:40]}...{access_token[-10:]}")
    print(f"  refreshToken:  {refresh_token[:40]}...{refresh_token[-10:]}")

    print("\n  Full values (copy-paste ready):\n")
    result = {
        "car_id": car_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }
    print(json.dumps(result, indent=2))
    print()


if __name__ == "__main__":
    main()
