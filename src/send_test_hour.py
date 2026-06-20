from datetime import datetime, timedelta
from house_sim import make_sensor_event, send_events


def build_normal_hour():
    base = datetime.now().replace(minute=0, second=0, microsecond=0)

    return [
        make_sensor_event(base + timedelta(minutes=5), "pir_kitchen", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=8), "fridge_contact", "contact", "open", 1),
        make_sensor_event(base + timedelta(minutes=11), "fridge_contact", "contact", "closed", 0),
        make_sensor_event(base + timedelta(minutes=15), "stove_power", "power", "on", 1),
        make_sensor_event(base + timedelta(minutes=35), "stove_power", "power", "off", 0),
        make_sensor_event(base + timedelta(minutes=45), "pir_living_room", "motion", "detected", 1),
    ]

def build_low_hour():
    base = datetime.now().replace(minute=0, second=0, microsecond=0)

    return [
        make_sensor_event(base + timedelta(minutes=0), "pressure_bed_bedroom", "pressure", "occupied", 1),
        make_sensor_event(base + timedelta(minutes=40), "pressure_bed_bedroom", "pressure", "empty", 0),
    ]

def build_medium_hour():
    base = datetime.now().replace(minute=0, second=0, microsecond=0)

    return [
        make_sensor_event(base + timedelta(minutes=5), "pir_kitchen", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=8), "fridge_contact", "contact", "open", 1),
        make_sensor_event(base + timedelta(minutes=20), "fridge_contact", "contact", "closed", 0),
    ]


def build_critical_hour():
    base = datetime.now().replace(minute=0, second=0, microsecond=0)

    return [
        make_sensor_event(base + timedelta(minutes=5), "stove_power", "power", "on", 1),
        make_sensor_event(base + timedelta(minutes=12), "pir_bedroom", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=15), "pressure_bed_bedroom", "pressure", "occupied", 1),
    ]


if __name__ == "__main__":
    # Change this to: "normal", "medium", or "critical"
    scenario = "critical"

    if scenario == "normal":
        events = build_normal_hour()
    elif scenario == "medium":
        events = build_medium_hour()
    elif scenario == "critical":
        events = build_critical_hour()
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    send_events(events)
    print(f"Sent {len(events)} {scenario} test events to ThingsBoard.")