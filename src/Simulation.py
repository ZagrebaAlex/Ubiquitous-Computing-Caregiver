import json
import csv
import os
import random
from datetime import datetime, timedelta

TOPOLOGY_FILE = "sensor_topology.json"
SCENARIO_FOLDER = "scenarios"

OUTPUT_JSON = "sensor_simulation.json"
OUTPUT_CSV = "sensor_simulation.csv"

START_TIME = datetime(2026, 1, 1, 0, 0)
random.seed(42)


def load_json(path):
    with open(path, "r") as file:
        return json.load(file)


def get_sensor(topology, sensor_id):
    for sensor in topology["sensors"]:
        if sensor["sensor_id"] == sensor_id:
            return sensor

    raise ValueError(f"Sensor not found in topology: {sensor_id}")


def add_random_jitter(timestamp, jitter_minutes):
    if jitter_minutes <= 0:
        return timestamp

    random_offset = random.randint(-jitter_minutes, jitter_minutes)
    return timestamp + timedelta(minutes=random_offset)


def load_scenario(path, topology, day_offset):
    scenario_data = load_json(path)

    scenario_name = scenario_data["scenario"]
    danger_level = scenario_data["danger_level"]

    jitter_minutes = scenario_data.get("jitter_minutes", 0)
    base_day = START_TIME + timedelta(days=day_offset)

    events = []

    for event in scenario_data["events"]:
        sensor = get_sensor(topology, event["sensor_id"])

        timestamp = base_day + timedelta(minutes=event["offset_minutes"])
        timestamp = add_random_jitter(timestamp, event.get("jitter_minutes", jitter_minutes))

        events.append({
            "timestamp": timestamp.isoformat(),
            "home_id": topology["home_id"],
            "sensor_id": sensor["sensor_id"],
            "sensor_type": sensor["sensor_type"],
            "location": sensor["location"],
            "value": event["value"],
            "scenario": scenario_name,
            "danger_level": danger_level
        })

    return events


def generate_alerts(events):
    alerts = []

    fridge_open_time = None
    last_kitchen_motion = None

    for event in sorted(events, key=lambda x: x["timestamp"]):
        timestamp = datetime.fromisoformat(event["timestamp"])

        if event["sensor_id"] == "pir_kitchen" and event["value"] == "MOTION":
            last_kitchen_motion = timestamp

        if event["sensor_id"] == "fridge_contact":
            if event["value"] == "OPEN":
                fridge_open_time = timestamp

            elif event["value"] == "CLOSED":
                fridge_open_time = None

            elif event["value"] == "STILL_OPEN" and fridge_open_time:
                if timestamp - fridge_open_time > timedelta(minutes=30):
                    alerts.append({
                        "timestamp": event["timestamp"],
                        "scenario": event["scenario"],
                        "severity": "MEDIUM",
                        "type": "FRIDGE_LEFT_OPEN",
                        "message": "Fridge left open for more than 30 minutes.",
                        "recommended_action": "Check whether the resident forgot to close the fridge."
                    })

        if event["sensor_id"] == "stove_power":
            if isinstance(event["value"], int) and event["value"] > 0:
                if last_kitchen_motion and timestamp - last_kitchen_motion > timedelta(minutes=15):
                    alerts.append({
                        "timestamp": event["timestamp"],
                        "scenario": event["scenario"],
                        "severity": "HIGH",
                        "type": "STOVE_UNATTENDED",
                        "message": "Stove appears to be on while there is no recent kitchen activity.",
                        "recommended_action": "Contact the resident or caretaker immediately."
                    })

        if event["value"] in ["NO_MOTION_6H", "STILL_ON_COUCH_6H"]:
            alerts.append({
                "timestamp": event["timestamp"],
                "scenario": event["scenario"],
                "severity": "MEDIUM",
                "type": "SEDENTARY_BEHAVIOUR",
                "message": "Resident appears inactive or seated for more than 6 hours.",
                "recommended_action": "Check if the resident is okay."
            })

        if (
            event["sensor_id"] == "entrance_door"
            and event["value"] == "OPEN"
            and 0 <= timestamp.hour <= 5
        ):
            alerts.append({
                "timestamp": event["timestamp"],
                "scenario": event["scenario"],
                "severity": "HIGH",
                "type": "NIGHT_EXIT",
                "message": "Entrance door opened during night hours.",
                "recommended_action": "Verify resident safety immediately."
            })

    return alerts


def save_outputs(events, alerts):
    events.sort(key=lambda x: x["timestamp"])

    output = {
        "sensor_events": events,
        "alerts": alerts
    }

    with open(OUTPUT_JSON, "w") as file:
        json.dump(output, file, indent=4)

    with open(OUTPUT_CSV, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "timestamp",
            "home_id",
            "sensor_id",
            "sensor_type",
            "location",
            "value",
            "scenario",
            "danger_level"
        ])

        writer.writeheader()
        writer.writerows(events)


def main():
    topology = load_json(TOPOLOGY_FILE)

    scenario_files = [
        "normal_day.json",
        "subtle_decline.json",
        "acute_hazard.json"
    ]

    events = []

    for day_offset, filename in enumerate(scenario_files):
        path = os.path.join(SCENARIO_FOLDER, filename)
        events.extend(load_scenario(path, topology, day_offset))

    events.sort(key=lambda x: x["timestamp"])
    alerts = generate_alerts(events)

    save_outputs(events, alerts)

    print(f"Generated {len(events)} sensor events")
    print(f"Generated {len(alerts)} alerts")
    print(f"Saved output to {OUTPUT_JSON}")
    print(f"Saved output to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()