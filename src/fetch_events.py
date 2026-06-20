import os
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

THINGSBOARD_HOST = os.getenv("THINGSBOARD_HOST", "http://localhost:9090")
THINGSBOARD_USERNAME = os.getenv("THINGSBOARD_USERNAME", "tenant@thingsboard.org")
THINGSBOARD_PASSWORD = os.getenv("THINGSBOARD_PASSWORD", "tenant")
THINGSBOARD_DEVICE_NAME = os.getenv("THINGSBOARD_DEVICE_NAME", "apartment_01")

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "sensor_data.json"

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


def login() -> str:
    response = requests.post(
        f"{THINGSBOARD_HOST}/api/auth/login",
        json={
            "username": THINGSBOARD_USERNAME,
            "password": THINGSBOARD_PASSWORD,
        },
        timeout=15,
    )
    response.raise_for_status()
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
    response.raise_for_status()
    return response.json()["id"]["id"]


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
    response.raise_for_status()
    return response.json()


def from_ms(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")


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


def fetch_events(lookback_hours: int) -> list[dict]:
    end_ts = to_ms(datetime.now())
    start_ts = to_ms(datetime.now() - timedelta(hours=lookback_hours))

    token = login()
    device_id = get_device_id(token, THINGSBOARD_DEVICE_NAME)
    raw = fetch_timeseries(token, device_id, start_ts, end_ts)

    return reconstruct_events(raw)


def save_events(events: list[dict], path: Path = OUTPUT_PATH) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(events, file, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()

    events = fetch_events(args.hours)
    save_events(events)

    print(f"Fetched {len(events)} events.")
    print(f"Saved to {OUTPUT_PATH}")