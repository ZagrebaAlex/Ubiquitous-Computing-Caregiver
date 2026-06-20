import os
import requests
from datetime import datetime, timedelta


THINGSBOARD_HOST = os.getenv("THINGSBOARD_HOST", "http://localhost:9090")
THINGSBOARD_USERNAME = os.getenv("THINGSBOARD_USERNAME", "tenant@thingsboard.org")
THINGSBOARD_PASSWORD = os.getenv("THINGSBOARD_PASSWORD", "tenant")
THINGSBOARD_DEVICE_NAME = os.getenv("THINGSBOARD_DEVICE_NAME", "apartment_01")

TELEMETRY_KEYS = [
    "sensor_id",
    "sensor_type",
    "location",
    "event_type",
    "state",
    "value"
]


def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def from_ms(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000).isoformat()


def login() -> str:
    response = requests.post(
        f"{THINGSBOARD_HOST}/api/auth/login",
        json={
            "username": THINGSBOARD_USERNAME,
            "password": THINGSBOARD_PASSWORD
        },
        timeout=20
    )

    if response.status_code >= 300:
        raise RuntimeError(f"ThingsBoard login failed: {response.status_code} {response.text}")

    return response.json()["token"]


def headers(jwt_token: str) -> dict:
    return {
        "X-Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }


def get_device_id(jwt_token: str, device_name: str = THINGSBOARD_DEVICE_NAME) -> str:
    response = requests.get(
        f"{THINGSBOARD_HOST}/api/tenant/devices",
        headers=headers(jwt_token),
        params={"deviceName": device_name},
        timeout=20
    )

    if response.status_code >= 300:
        raise RuntimeError(f"Device lookup failed: {response.status_code} {response.text}")

    device = response.json()

    if "id" not in device or "id" not in device["id"]:
        raise RuntimeError(f"Device not found: {device_name}")

    return device["id"]["id"]


def fetch_raw_timeseries(jwt_token: str, device_id: str, start_ts: int, end_ts: int) -> dict:
    response = requests.get(
        f"{THINGSBOARD_HOST}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
        headers=headers(jwt_token),
        params={
            "keys": ",".join(TELEMETRY_KEYS),
            "startTs": start_ts,
            "endTs": end_ts,
            "limit": 10000,
            "agg": "NONE"
        },
        timeout=30
    )

    if response.status_code >= 300:
        raise RuntimeError(f"Telemetry fetch failed: {response.status_code} {response.text}")

    return response.json()


def reconstruct_events(raw: dict) -> list[dict]:
    events_by_ts = {}

    for key, items in raw.items():
        for item in items:
            ts = int(item["ts"])

            if ts not in events_by_ts:
                events_by_ts[ts] = {
                    "ts": ts,
                    "timestamp": from_ms(ts)
                }

            events_by_ts[ts][key] = item.get("value")

    events = list(events_by_ts.values())
    events.sort(key=lambda event: event["ts"])

    return events


def fetch_device_events(lookback_hours: int) -> list[dict]:
    end_ts = to_ms(datetime.now())
    start_ts = to_ms(datetime.now() - timedelta(hours=lookback_hours))

    jwt_token = login()
    device_id = get_device_id(jwt_token)
    raw = fetch_raw_timeseries(jwt_token, device_id, start_ts, end_ts)

    return reconstruct_events(raw)