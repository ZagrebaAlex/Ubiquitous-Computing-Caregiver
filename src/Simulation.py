import json
import csv
import os
import random
from datetime import datetime, timedelta

TOPOLOGY_FILE = "sensor_topology.json"
SCENARIO_FOLDER = "Data"

OUTPUT_JSON = "sensor_simulation_10days.json"
OUTPUT_CSV = "sensor_simulation_10days.csv"
OUTPUT_ALERTS_JSON = "alerts.json"

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
    return timestamp + timedelta(minutes=random.randint(-jitter_minutes, jitter_minutes))


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
        timestamp = add_random_jitter(
            timestamp,
            event.get("jitter_minutes", jitter_minutes)
        )

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
    water_on_time = None

    alert_counter = 1

    def add_alert(timestamp, scenario, severity, alert_type, message, recommended_action):
        nonlocal alert_counter

        alerts.append({
            "alert_id": f"ALT-{alert_counter:04d}",
            "timestamp": timestamp,
            "scenario": scenario,
            "severity": severity,
            "type": alert_type,
            "status": "ACTIVE",
            "message": message,
            "recommended_action": recommended_action
        })

        alert_counter += 1

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
                    add_alert(
                        event["timestamp"],
                        event["scenario"],
                        "MEDIUM",
                        "FRIDGE_LEFT_OPEN",
                        "Fridge left open for more than 30 minutes.",
                        "Check whether the resident forgot to close the fridge."
                    )

        if (
            event["sensor_id"] == "stove_power"
            and isinstance(event["value"], int)
            and event["value"] > 0
        ):
            if last_kitchen_motion and timestamp - last_kitchen_motion > timedelta(minutes=15):
                add_alert(
                    event["timestamp"],
                    event["scenario"],
                    "HIGH",
                    "STOVE_UNATTENDED",
                    "Stove appears to be on while there is no recent kitchen activity.",
                    "Contact the resident or caretaker immediately."
                )

        if event["sensor_id"].startswith("waterflow_"):
            if event["value"] == "ON":
                water_on_time = timestamp

            elif event["value"] == "OFF":
                water_on_time = None

            elif event["value"] == "STILL_ON" and water_on_time:
                if timestamp - water_on_time > timedelta(minutes=20):
                    add_alert(
                        event["timestamp"],
                        event["scenario"],
                        "HIGH",
                        "WATER_LEFT_RUNNING",
                        "Bathroom water appears to have been left running.",
                        "Check the bathroom immediately."
                    )

        if event["value"] in ["NO_MOTION_6H", "STILL_ON_COUCH_6H"]:
            add_alert(
                event["timestamp"],
                event["scenario"],
                "MEDIUM",
                "SEDENTARY_BEHAVIOUR",
                "Resident appears inactive or seated for more than 6 hours.",
                "Check if the resident is okay."
            )

        if event["value"] == "NO_ACTIVITY" and event["sensor_id"] == "medicine_cabinet":
            add_alert(
                event["timestamp"],
                event["scenario"],
                "MEDIUM",
                "MISSED_MEDICATION",
                "No medicine cabinet activity was detected near the expected medication time.",
                "Remind the resident to take medication or contact the caretaker."
            )

        if event["value"] == "NO_MORNING_HYGIENE":
            add_alert(
                event["timestamp"],
                event["scenario"],
                "MEDIUM",
                "MISSED_HYGIENE_ROUTINE",
                "Expected morning hygiene activity was not detected.",
                "Check whether the resident needs assistance."
            )

        if (
            event["sensor_id"] == "entrance_door"
            and event["value"] == "OPEN"
            and 0 <= timestamp.hour <= 5
        ):
            add_alert(
                event["timestamp"],
                event["scenario"],
                "HIGH",
                "NIGHT_EXIT",
                "Entrance door opened during night hours.",
                "Verify resident safety immediately."
            )

    return alerts


def save_outputs(events, alerts):
    events.sort(key=lambda x: x["timestamp"])

    with open(OUTPUT_JSON, "w") as file:
        json.dump(
            {
                "generated_at": datetime.now().isoformat(),
                "sensor_events": events
            },
            file,
            indent=4
        )

    with open(OUTPUT_ALERTS_JSON, "w") as file:
        json.dump(
            {
                "generated_at": datetime.now().isoformat(),
                "total_alerts": len(alerts),
                "alerts": alerts
            },
            file,
            indent=4
        )

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

    scenario_files = sorted([
        f for f in os.listdir(SCENARIO_FOLDER)
        if f.endswith(".json")
    ])

    events = []

    for day_offset, filename in enumerate(scenario_files):
        path = os.path.join(SCENARIO_FOLDER, filename)
        events.extend(load_scenario(path, topology, day_offset))

    alerts = generate_alerts(events)
    save_outputs(events, alerts)

    print(f"Loaded {len(scenario_files)} daily scenario files")
    print(f"Generated {len(events)} sensor events")
    print(f"Generated {len(alerts)} alerts")
    print(f"Saved events JSON: {OUTPUT_JSON}")
    print(f"Saved alerts JSON: {OUTPUT_ALERTS_JSON}")
    print(f"Saved CSV: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()