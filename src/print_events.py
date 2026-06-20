
import os
import requests
from datetime import datetime, timedelta


THINGSBOARD_HOST = os.getenv("THINGSBOARD_HOST", "http://localhost:9090")
THINGSBOARD_USERNAME = os.getenv("THINGSBOARD_USERNAME", "tenant@thingsboard.org")
THINGSBOARD_PASSWORD = os.getenv("THINGSBOARD_PASSWORD", "tenant")
THINGSBOARD_DEVICE_NAME = os.getenv("THINGSBOARD_DEVICE_NAME", "apartment_01")

LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "24"))

TELEMETRY_KEYS = [
    "sensor_id",
    "sensor_type",
    "location",
    "event_type",
    "state",
    "value",
]


def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def from_ms(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")


def login() -> str:
    response = requests.post(
        f"{THINGSBOARD_HOST}/api/auth/login",
        json={
            "username": THINGSBOARD_USERNAME,
            "password": THINGSBOARD_PASSWORD,
        },
        timeout=15,
    )

    if response.status_code >= 300:
        raise RuntimeError(f"Login failed: {response.status_code} {response.text}")

    return response.json()["token"]


def auth_headers(token: str) -> dict:
    return {
        "X-Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def get_device_id(token: str, device_name: str) -> str:
    response = requests.get(
        f"{THINGSBOARD_HOST}/api/tenant/devices",
        headers=auth_headers(token),
        params={"deviceName": device_name},
        timeout=15,
    )

    if response.status_code >= 300:
        raise RuntimeError(
            f"Device lookup failed: {response.status_code} {response.text}"
        )

    device = response.json()

    if "id" not in device or "id" not in device["id"]:
        raise RuntimeError(f"Device not found: {device_name}")

    return device["id"]["id"]


def fetch_timeseries(token: str, device_id: str, start_ts: int, end_ts: int) -> dict:
    response = requests.get(
        f"{THINGSBOARD_HOST}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
        headers=auth_headers(token),
        params={
            "keys": ",".join(TELEMETRY_KEYS),
            "startTs": start_ts,
            "endTs": end_ts,
            "limit": 10000,
            "agg": "NONE",
        },
        timeout=20,
    )

    if response.status_code >= 300:
        raise RuntimeError(
            f"Telemetry fetch failed: {response.status_code} {response.text}"
        )

    return response.json()


def reconstruct_events(raw: dict) -> list[dict]:
    events_by_ts = {}

    for key, items in raw.items():
        for item in items:
            ts = int(item["ts"])

            if ts not in events_by_ts:
                events_by_ts[ts] = {"ts": ts}

            events_by_ts[ts][key] = item.get("value")

    events = list(events_by_ts.values())
    events.sort(key=lambda event: event["ts"])

    return events


def print_events(events: list[dict]) -> None:
    if not events:
        print("No telemetry events found.")
        return

    print()
    print(f"Fetched {len(events)} reconstructed telemetry events.")
    print()

    for event in events:
        print(
            f"{from_ms(event['ts'])} | "
            f"{event.get('sensor_id', '-')} | "
            f"{event.get('sensor_type', '-')} | "
            f"{event.get('location', '-')} | "
            f"{event.get('event_type', '-')} | "
            f"{event.get('state', '-')} | "
            f"{event.get('value', '-')}"
        )


def main() -> None:
    end_ts = to_ms(datetime.now())
    start_ts = to_ms(datetime.now() - timedelta(hours=LOOKBACK_HOURS))

    print("ThingsBoard host:", THINGSBOARD_HOST)
    print("Device:", THINGSBOARD_DEVICE_NAME)
    print("Lookback hours:", LOOKBACK_HOURS)

    token = login()
    device_id = get_device_id(token, THINGSBOARD_DEVICE_NAME)
    raw = fetch_timeseries(token, device_id, start_ts, end_ts)
    events = reconstruct_events(raw)

    print_events(events)


if __name__ == "__main__":
    main()