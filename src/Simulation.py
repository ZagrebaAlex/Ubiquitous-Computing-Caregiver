import json
import random
import csv
from datetime import datetime, timedelta

INPUT_TOPOLOGY_FILE = "sensor_topology.json"
OUTPUT_JSON_FILE = "sensor_simulation.json"
OUTPUT_CSV_FILE = "sensor_simulation.csv"

START_TIME = datetime(2026, 1, 1, 0, 0)


def load_topology(filename):
    with open(filename, "r") as file:
        return json.load(file)


def add_event(events, timestamp, sensor, value, scenario, danger_level):
    events.append({
        "timestamp": timestamp.isoformat(),
        "sensor_id": sensor["sensor_id"],
        "sensor_type": sensor["sensor_type"],
        "location": sensor["location"],
        "value": value,
        "scenario": scenario,
        "danger_level": danger_level
    })


def find_sensor(topology, sensor_type=None, location=None):
    for sensor in topology["sensors"]:
        if sensor_type and sensor["sensor_type"] != sensor_type:
            continue
        if location and sensor["location"] != location:
            continue
        return sensor
    return None


def random_motion(events, topology, start_time, end_time, scenario, danger_level):
    pir_sensors = [
        s for s in topology["sensors"]
        if s["sensor_type"] == "PIR"
    ]

    current = start_time

    while current < end_time:
        sensor = random.choice(pir_sensors)

        add_event(
            events,
            current,
            sensor,
            "MOTION",
            scenario,
            danger_level
        )

        current += timedelta(minutes=random.randint(15, 90))


def generate_normal_day(events, topology):
    scenario = "Normal Day"
    danger = "LOW"
    base = START_TIME

    bedroom = find_sensor(topology, "PIR", "Bedroom")
    bathroom = find_sensor(topology, "PIR", "Bathroom")
    kitchen = find_sensor(topology, "PIR", "Kitchen")
    living = find_sensor(topology, "PIR", "Living Room")
    fridge = find_sensor(topology, "CONTACT", "Kitchen")
    stove = find_sensor(topology, "POWER", "Kitchen")

    add_event(events, base.replace(hour=7), bedroom, "WAKE_UP", scenario, danger)
    add_event(events, base.replace(hour=7, minute=10), bathroom, "MOTION", scenario, danger)
    add_event(events, base.replace(hour=7, minute=25), kitchen, "MOTION", scenario, danger)

    random_motion(
        events,
        topology,
        base.replace(hour=8),
        base.replace(hour=22),
        scenario,
        danger
    )

    for hour in [8, 13, 19]:
        meal_time = base.replace(hour=hour) + timedelta(minutes=random.randint(-10, 10))

        add_event(events, meal_time, fridge, "OPEN", scenario, danger)
        add_event(events, meal_time + timedelta(minutes=random.randint(1, 3)), fridge, "CLOSED", scenario, danger)

        add_event(events, meal_time + timedelta(minutes=5), stove, random.randint(900, 1800), scenario, danger)
        add_event(events, meal_time + timedelta(minutes=random.randint(20, 35)), stove, 0, scenario, danger)

    add_event(events, base.replace(hour=22, minute=30), bathroom, "MOTION", scenario, danger)
    add_event(events, base.replace(hour=22, minute=45), bedroom, "SLEEP", scenario, danger)


def generate_subtle_decline(events, topology):
    scenario = "Subtle Decline"
    danger = "MEDIUM"
    base = START_TIME + timedelta(days=1)

    bedroom = find_sensor(topology, "PIR", "Bedroom")
    bathroom = find_sensor(topology, "PIR", "Bathroom")
    living = find_sensor(topology, "PIR", "Living Room")
    fridge = find_sensor(topology, "CONTACT", "Kitchen")

    add_event(events, base.replace(hour=8), bedroom, "WAKE_UP", scenario, danger)
    add_event(events, base.replace(hour=8, minute=20), bathroom, "MOTION", scenario, danger)

    random_motion(
        events,
        topology,
        base.replace(hour=8),
        base.replace(hour=11),
        scenario,
        danger
    )

    fridge_open_time = base.replace(hour=9)
    add_event(events, fridge_open_time, fridge, "OPEN", scenario, danger)
    add_event(events, fridge_open_time + timedelta(hours=3), fridge, "STILL_OPEN", scenario, danger)
    add_event(events, fridge_open_time + timedelta(hours=8), fridge, "CLOSED", scenario, danger)

    add_event(events, base.replace(hour=11), living, "INACTIVE_START", scenario, danger)
    add_event(events, base.replace(hour=17, minute=30), living, "INACTIVE_END", scenario, danger)


def generate_acute_hazard(events, topology):
    scenario = "Acute Hazard"
    danger = "HIGH"
    base = START_TIME + timedelta(days=2)

    kitchen = find_sensor(topology, "PIR", "Kitchen")
    living = find_sensor(topology, "PIR", "Living Room")
    bedroom = find_sensor(topology, "PIR", "Bedroom")
    stove = find_sensor(topology, "POWER", "Kitchen")
    entrance = find_sensor(topology, "CONTACT", "Entrance")

    add_event(events, base.replace(hour=18), kitchen, "MOTION", scenario, danger)
    add_event(events, base.replace(hour=18, minute=1), stove, random.randint(1200, 2200), scenario, danger)

    add_event(events, base.replace(hour=18, minute=5), living, "MOTION", scenario, danger)
    add_event(events, base.replace(hour=18, minute=20), bedroom, "MOTION", scenario, danger)
    add_event(events, base.replace(hour=18, minute=45), stove, random.randint(1200, 2200), scenario, danger)

    add_event(events, base.replace(hour=3), entrance, "OPEN", scenario, danger)
    add_event(events, base.replace(hour=3, minute=1), entrance, "CLOSED", scenario, danger)


def generate_alerts(events):
    alerts = []

    fridge_open_time = None
    stove_on_time = None
    last_kitchen_motion = None

    for event in events:
        timestamp = datetime.fromisoformat(event["timestamp"])

        if event["sensor_type"] == "PIR" and event["location"] == "Kitchen":
            last_kitchen_motion = timestamp

        if event["sensor_type"] == "CONTACT" and event["location"] == "Kitchen":
            if event["value"] == "OPEN":
                fridge_open_time = timestamp

            elif event["value"] == "CLOSED":
                fridge_open_time = None

            elif event["value"] == "STILL_OPEN":
                if fridge_open_time and timestamp - fridge_open_time > timedelta(minutes=30):
                    alerts.append({
                        "timestamp": event["timestamp"],
                        "alert": "Fridge left open for more than 30 minutes",
                        "severity": "MEDIUM"
                    })

        if event["sensor_type"] == "POWER" and event["location"] == "Kitchen":
            if isinstance(event["value"], int) and event["value"] > 0:
                if stove_on_time is None:
                    stove_on_time = timestamp

                if last_kitchen_motion and timestamp - last_kitchen_motion > timedelta(minutes=15):
                    alerts.append({
                        "timestamp": event["timestamp"],
                        "alert": "Stove left ON unattended",
                        "severity": "HIGH"
                    })

            elif event["value"] == 0:
                stove_on_time = None

        if event["value"] == "INACTIVE_END":
            alerts.append({
                "timestamp": event["timestamp"],
                "alert": "Resident inactive for more than 6 hours",
                "severity": "MEDIUM"
            })

        if (
            event["sensor_type"] == "CONTACT"
            and event["location"] == "Entrance"
            and event["value"] == "OPEN"
        ):
            hour = timestamp.hour
            if 0 <= hour <= 5:
                alerts.append({
                    "timestamp": event["timestamp"],
                    "alert": "Unexpected entrance door opening during night",
                    "severity": "HIGH"
                })

    return alerts


def save_outputs(events, alerts):
    events.sort(key=lambda e: e["timestamp"])

    output = {
        "sensor_events": events,
        "alerts": alerts
    }

    with open(OUTPUT_JSON_FILE, "w") as file:
        json.dump(output, file, indent=4)

    with open(OUTPUT_CSV_FILE, "w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "timestamp",
                "sensor_id",
                "sensor_type",
                "location",
                "value",
                "scenario",
                "danger_level"
            ]
        )
        writer.writeheader()
        writer.writerows(events)


def main():
    topology = load_topology(INPUT_TOPOLOGY_FILE)

    events = []

    generate_normal_day(events, topology)
    generate_subtle_decline(events, topology)
    generate_acute_hazard(events, topology)

    events.sort(key=lambda e: e["timestamp"])
    alerts = generate_alerts(events)

    save_outputs(events, alerts)

    print(f"Generated {len(events)} sensor events")
    print(f"Generated {len(alerts)} alerts")
    print(f"Saved: {OUTPUT_JSON_FILE}")
    print(f"Saved: {OUTPUT_CSV_FILE}")


if __name__ == "__main__":
    main()