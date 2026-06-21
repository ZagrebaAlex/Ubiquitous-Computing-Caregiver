import os
import json
import random
import requests
from pathlib import Path
from dotenv import load_dotenv

from datetime import datetime, timedelta, time

load_dotenv()


THINGSBOARD_HOST = os.getenv("THINGSBOARD_HOST", "http://localhost:9090")
THINGSBOARD_ACCESS_TOKEN = os.getenv(
    "THINGSBOARD_ACCESS_TOKEN",
    "RPSsFLY6KSl5VakoEYWS"
)

TELEMETRY_URL = f"{THINGSBOARD_HOST}/api/v1/{THINGSBOARD_ACCESS_TOKEN}/telemetry"

DAYS_TO_SIMULATE = 8
HAZARD_SCENARIO_PROBABILITY = 0.10
DECLINE_SCENARIO_PROBABILITY = 0.30
REAL_TIME_MODE = False
REAL_TIME_DELAY_SECONDS = 0.1

TOPOLOGY_FILE = Path(__file__).parent / "sensor_topology.json"


def load_sensor_topology(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Topology file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as file:
        topology = json.load(file)

    if "sensors" not in topology:
        raise ValueError("sensor_topology.json is missing 'sensors'")

    sensors = {}

    for sensor in topology["sensors"]:
        sensor_id = sensor.get("sensor_id")
        sensor_type = sensor.get("sensor_type")
        location = sensor.get("location")

        if not sensor_id or not sensor_type or not location:
            raise ValueError(f"Invalid sensor entry in topology: {sensor}")

        sensors[sensor_id] = {
            "sensor_type": sensor_type,
            "location": location
        }

    return sensors


SENSORS = load_sensor_topology(TOPOLOGY_FILE)


def to_timestamp_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def random_time_on_day(day: datetime, hour: int, minute_window: int = 30) -> datetime:
    return datetime.combine(day.date(), time(hour=hour)) + timedelta(
        minutes=random.randint(0, minute_window)
    )


def make_sensor_event(
    dt: datetime,
    sensor_id: str,
    event_type: str,
    state: str,
    value
) -> dict:
    if sensor_id not in SENSORS:
        raise KeyError(f"Sensor '{sensor_id}' does not exist in {TOPOLOGY_FILE}")

    sensor = SENSORS[sensor_id]

    return {
        "ts": to_timestamp_ms(dt),
        "values": {
            "sensor_id": sensor_id,
            "sensor_type": sensor["sensor_type"],
            "location": sensor["location"],
            "event_type": event_type,
            "state": state,
            "value": value
        }
    }


def send_event(event: dict) -> None:
    response = requests.post(TELEMETRY_URL, json=event, timeout=10)

    if response.status_code >= 300:
        raise RuntimeError(
            f"ThingsBoard telemetry request failed: {response.status_code} {response.text}"
        )

    event_time = datetime.fromtimestamp(event["ts"] / 1000)
    values = event["values"]

    print(
        f"[{event_time}] "
        f"{values['sensor_id']} | "
        f"{values['event_type']} | "
        f"{values['state']} | "
        f"{values['value']}"
    )


def send_events(events: list[dict]) -> None:
    events = sorted(events, key=lambda item: item["ts"])

    for event in events:
        send_event(event)

        if REAL_TIME_MODE:
            import time as time_module
            time_module.sleep(REAL_TIME_DELAY_SECONDS)


def generate_sleep(day: datetime) -> list[dict]:
    sleep_start = datetime.combine(
        day.date(),
        time(hour=23, minute=random.randint(0, 40))
    )

    sleep_end = sleep_start + timedelta(hours=random.uniform(6, 8))

    return [
        make_sensor_event(
            sleep_start,
            "pressure_bed_bedroom",
            "pressure",
            "occupied",
            1
        ),
        make_sensor_event(
            sleep_end,
            "pressure_bed_bedroom",
            "pressure",
            "empty",
            0
        )
    ]


def generate_medicine(day: datetime) -> list[dict]:
    return [
        make_sensor_event(
            random_time_on_day(day, 8, 60),
            "medicine_cabinet",
            "vibration",
            "detected",
            1
        )
    ]


def generate_meals(day: datetime) -> list[dict]:
    events = []

    for hour in [8, 13, 19]:
        meal_time = random_time_on_day(day, hour, 45)

        events.extend([
            make_sensor_event(
                meal_time,
                "pir_kitchen",
                "motion",
                "detected",
                1
            ),
            make_sensor_event(
                meal_time + timedelta(minutes=2),
                "fridge_contact",
                "contact",
                "open",
                1
            ),
            make_sensor_event(
                meal_time + timedelta(minutes=5),
                "fridge_contact",
                "contact",
                "closed",
                0
            )
        ])

        if random.random() < 0.55:
            stove_on = meal_time + timedelta(minutes=8)
            stove_off = stove_on + timedelta(minutes=random.randint(15, 35))

            events.extend([
                make_sensor_event(
                    stove_on,
                    "stove_power",
                    "power",
                    "on",
                    1
                ),
                make_sensor_event(
                    stove_off,
                    "stove_power",
                    "power",
                    "off",
                    0
                )
            ])

    return events


def generate_bathroom_and_hygiene(day: datetime) -> list[dict]:
    events = []

    toilet_time = random_time_on_day(day, 7, 60)
    shower_time = random_time_on_day(day, 9, 90)

    events.extend([
        make_sensor_event(
            toilet_time,
            "pir_bathroom",
            "motion",
            "detected",
            1
        ),
        make_sensor_event(
            toilet_time + timedelta(minutes=2),
            "waterflow_toilet",
            "waterflow",
            "active",
            1
        ),
        make_sensor_event(
            toilet_time + timedelta(minutes=3),
            "waterflow_toilet",
            "waterflow",
            "inactive",
            0
        ),
        make_sensor_event(
            toilet_time + timedelta(minutes=4),
            "waterflow_sink",
            "waterflow",
            "active",
            1
        ),
        make_sensor_event(
            toilet_time + timedelta(minutes=5),
            "waterflow_sink",
            "waterflow",
            "inactive",
            0
        ),
        make_sensor_event(
            shower_time,
            "waterflow_bathtub",
            "waterflow",
            "active",
            1
        ),
        make_sensor_event(
            shower_time + timedelta(minutes=random.randint(8, 15)),
            "waterflow_bathtub",
            "waterflow",
            "inactive",
            0
        )
    ])

    return events


def generate_balcony_and_air(day: datetime) -> list[dict]:
    balcony_door_open = random_time_on_day(day, 11, 90)
    balcony_visit = random_time_on_day(day, 17, 90)

    return [
        make_sensor_event(
            balcony_door_open,
            "door_balcony_livingroom",
            "contact",
            "open",
            1
        ),
        make_sensor_event(
            balcony_door_open + timedelta(minutes=random.randint(60, 90)),
            "door_balcony_livingroom",
            "contact",
            "closed",
            0
        ),
        make_sensor_event(
            balcony_visit,
            "pir_balcony",
            "motion",
            "detected",
            1
        ),
        make_sensor_event(
            balcony_visit + timedelta(minutes=random.randint(15, 30)),
            "pir_balcony",
            "motion",
            "not_detected",
            0
        )
    ]


def generate_room_movement(day: datetime) -> list[dict]:
    events = []

    movement_sensors = [
        "pir_bedroom",
        "pir_living_room",
        "pir_kitchen",
        "pir_bathroom"
    ]

    for _ in range(random.randint(10, 18)):
        events.append(
            make_sensor_event(
                random_time_on_day(day, random.randint(9, 21), 59),
                random.choice(movement_sensors),
                "motion",
                "detected",
                1
            )
        )

    return events


def generate_normal_day(day: datetime) -> list[dict]:
    events = []

    events.extend(generate_sleep(day))
    events.extend(generate_medicine(day))
    events.extend(generate_meals(day))
    events.extend(generate_bathroom_and_hygiene(day))
    events.extend(generate_balcony_and_air(day))
    events.extend(generate_room_movement(day))

    return events


def inject_decline_like_sequence(day: datetime) -> list[dict]:
    events = []

    scenario = random.choice([
        "fridge_open_long",
        "long_couch_sitting",
        "sink_running_long"
    ])

    if scenario == "fridge_open_long":
        start = random_time_on_day(day, 14, 30)

        events.extend([
            make_sensor_event(
                start,
                "fridge_contact",
                "contact",
                "open",
                1
            ),
            make_sensor_event(
                start + timedelta(minutes=45),
                "fridge_contact",
                "contact",
                "closed",
                0
            )
        ])

    elif scenario == "long_couch_sitting":
        start = random_time_on_day(day, 12, 60)

        events.extend([
            make_sensor_event(
                start,
                "couch_pressure_living_room",
                "pressure",
                "occupied",
                1
            ),
            make_sensor_event(
                start + timedelta(hours=4),
                "couch_pressure_living_room",
                "pressure",
                "empty",
                0
            )
        ])

    elif scenario == "sink_running_long":
        start = random_time_on_day(day, 16, 45)

        events.extend([
            make_sensor_event(
                start,
                "waterflow_sink",
                "waterflow",
                "active",
                1
            ),
            make_sensor_event(
                start + timedelta(minutes=25),
                "waterflow_sink",
                "waterflow",
                "inactive",
                0
            )
        ])

    return events


def inject_hazard_like_sequence(day: datetime) -> list[dict]:
    events = []

    scenario = random.choice([
        "stove_on_then_sleep",
        "stove_on_then_exit",
        "very_long_sleep",
        "night_exit",
        "entrance_door_open_at_night"
    ])

    if scenario == "stove_on_then_sleep":
        stove_on = datetime.combine(
            day.date(),
            time(hour=22, minute=random.randint(15, 45))
        )

        events.extend([
            make_sensor_event(
                stove_on,
                "stove_power",
                "power",
                "on",
                1
            ),
            make_sensor_event(
                stove_on + timedelta(minutes=20),
                "pressure_bed_bedroom",
                "pressure",
                "occupied",
                1
            ),
            make_sensor_event(
                stove_on + timedelta(minutes=90),
                "stove_power",
                "power",
                "off",
                0
            )
        ])

    elif scenario == "stove_on_then_exit":
        stove_on = random_time_on_day(day, 18, 30)

        events.extend([
            make_sensor_event(
                stove_on,
                "stove_power",
                "power",
                "on",
                1
            ),
            make_sensor_event(
                stove_on + timedelta(minutes=5),
                "entrance_door",
                "contact",
                "open",
                1
            ),
            make_sensor_event(
                stove_on + timedelta(minutes=6),
                "floor_mat",
                "pressure",
                "pressed",
                1
            ),
            make_sensor_event(
                stove_on + timedelta(minutes=7),
                "entrance_door",
                "contact",
                "closed",
                0
            ),
            make_sensor_event(
                stove_on + timedelta(minutes=75),
                "stove_power",
                "power",
                "off",
                0
            )
        ])

    elif scenario == "very_long_sleep":
        sleep_start = datetime.combine(day.date(), time(hour=21, minute=30))

        events.extend([
            make_sensor_event(
                sleep_start,
                "pressure_bed_bedroom",
                "pressure",
                "occupied",
                1
            ),
            make_sensor_event(
                sleep_start + timedelta(hours=11),
                "pressure_bed_bedroom",
                "pressure",
                "empty",
                0
            )
        ])

    elif scenario == "night_exit":
        exit_time = datetime.combine(
            day.date(),
            time(hour=random.choice([1, 2, 3]), minute=random.randint(0, 40))
        )

        events.extend([
            make_sensor_event(
                exit_time,
                "entrance_door",
                "contact",
                "open",
                1
            ),
            make_sensor_event(
                exit_time + timedelta(minutes=1),
                "floor_mat",
                "pressure",
                "pressed",
                1
            ),
            make_sensor_event(
                exit_time + timedelta(minutes=2),
                "entrance_door",
                "contact",
                "closed",
                0
            )
        ])

    elif scenario == "entrance_door_open_at_night":
        door_open = datetime.combine(
            day.date(),
            time(hour=2, minute=random.randint(0, 40))
        )

        events.extend([
            make_sensor_event(
                door_open,
                "entrance_door",
                "contact",
                "open",
                1
            ),
            make_sensor_event(
                door_open + timedelta(minutes=40),
                "entrance_door",
                "contact",
                "closed",
                0
            )
        ])

    return events


def build_simulation() -> list[dict]:
    all_events = []
    first_day = datetime.now() - timedelta(days=DAYS_TO_SIMULATE)

    for day_index in range(DAYS_TO_SIMULATE):
        day = first_day + timedelta(days=day_index)
        day_events = generate_normal_day(day)

        if random.random() < DECLINE_SCENARIO_PROBABILITY:
            day_events.extend(inject_decline_like_sequence(day))

        if random.random() < HAZARD_SCENARIO_PROBABILITY:
            day_events.extend(inject_hazard_like_sequence(day))

        all_events.extend(day_events)

    return all_events


if __name__ == "__main__":
    random.seed(42)

    print("Starting raw sensor simulator")
    print("ThingsBoard host:", THINGSBOARD_HOST)
    print("Topology file:", TOPOLOGY_FILE)
    print("Sensors:", len(SENSORS))
    print()

    simulation_events = build_simulation()

    print(f"Sending {len(simulation_events)} events...")
    print()

    send_events(simulation_events)

    print()
    print("Simulation completed.")
