import json
from pathlib import Path
from datetime import datetime, timedelta, time

BASE_DIR = Path(__file__).resolve().parent
SENSOR_DATA_PATH = BASE_DIR / "sensor_data.json"
OUTPUT_PATH = BASE_DIR / "rule_alerts.json"


SEVERITY_BY_ALERT = {
    "late_wakeup": "low",
    "late_medication": "low",
    "delayed_meal_activity": "low",
    "delayed_shower": "low",
    "delayed_sleep": "low",

    "fridge_left_open": "medium",
    "water_running_no_bathroom": "medium",
    "long_sedentary_period": "medium",
    "very_late_wakeup": "medium",
    "very_late_medication": "medium",
    "missed_meal_window": "medium",
    "multiple_routine_deviations": "medium",

    "stove_on_left_appartment": "critical",
    "exit_appartment_at_night": "critical",
    "door_open_at_night": "critical",
    "door_open_while_sleeping": "critical",
    "balcony_door_open_while_away": "critical",
}


def parse_time(event: dict) -> datetime:
    raw = event.get("timestamp")

    if not raw:
        ts = event.get("ts")
        if ts is None:
            raise ValueError(f"Event has neither timestamp nor ts: {event}")
        return datetime.fromtimestamp(int(ts) / 1000)

    raw = str(raw).strip()

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"Unsupported timestamp format: {raw}") from exc


def event_time_text(event: dict) -> str:
    return parse_time(event).strftime("%Y-%m-%dT%H:%M:%S")


def is_between(dt: datetime, start_time: time, end_time: time) -> bool:
    current = dt.time()

    if start_time <= end_time:
        return start_time <= current <= end_time

    return current >= start_time or current <= end_time


def event_is(event: dict, sensor_id: str | None = None, state: str | None = None) -> bool:
    if sensor_id is not None and event.get("sensor_id") != sensor_id:
        return False
    if state is not None and event.get("state") != state:
        return False
    return True


def make_alert(
    alert_name: str,
    timestamp: str,
    event: str,
    evidence: list[str],
    recommended_action: str,
) -> dict:
    return {
        "alert_name": alert_name,
        "severity": SEVERITY_BY_ALERT[alert_name],
        "timestamp": timestamp,
        "event": event,
        "evidence": evidence,
        "recommended_action": recommended_action,
    }


def check_fridge_left_open(events: list[dict]) -> list[dict]:
    alerts = []
    open_event = None

    for e in events:
        if event_is(e, "fridge_contact", "open"):
            open_event = e

        elif event_is(e, "fridge_contact", "closed") and open_event:
            duration = parse_time(e) - parse_time(open_event)

            if duration > timedelta(minutes=5):
                alerts.append(make_alert(
                    "fridge_left_open",
                    event_time_text(e),
                    "Fridge remained open for more than 5 minutes.",
                    [
                        f"Fridge opened at {event_time_text(open_event)}.",
                        f"Fridge closed at {event_time_text(e)}.",
                        f"Open duration was approximately {int(duration.total_seconds() / 60)} minutes."
                    ],
                    "Ask the resident or caregiver to check whether the fridge was closed properly."
                ))

            open_event = None

    if open_event:
        alerts.append(make_alert(
            "fridge_left_open",
            event_time_text(open_event),
            "Fridge was opened and no closing event was found in the available data.",
            [
                f"Fridge opened at {event_time_text(open_event)}.",
                "No fridge closed event appears after it in the available window."
            ],
            "Check the fridge status."
        ))

    return alerts


def check_stove_on_left_or_sleep(events: list[dict]) -> list[dict]:
    alerts = []
    stove_on_event = None
    already_alerted = False

    for e in events:
        if event_is(e, "stove_power", "on"):
            stove_on_event = e
            already_alerted = False

        elif event_is(e, "stove_power", "off"):
            stove_on_event = None
            already_alerted = False

        if stove_on_event and not already_alerted and event_is(e, "pressure_bed_bedroom", "occupied"):
            alerts.append(make_alert(
                "stove_on_left_appartment",
                event_time_text(e),
                "Stove appears to be on while the resident is in bed.",
                [
                    f"Stove turned on at {event_time_text(stove_on_event)}.",
                    f"Bed pressure became occupied at {event_time_text(e)}.",
                    "No stove off event was observed before bed occupancy."
                ],
                "Notify the caregiver immediately."
            ))
            already_alerted = True

        if stove_on_event and not already_alerted and event_is(e, "entrance_door", "open"):
            alerts.append(make_alert(
                "stove_on_left_appartment",
                event_time_text(e),
                "Stove appears to be on while the resident may be leaving the apartment.",
                [
                    f"Stove turned on at {event_time_text(stove_on_event)}.",
                    f"Entrance door opened at {event_time_text(e)}."
                ],
                "Notify the caregiver immediately."
            ))
            already_alerted = True

    return alerts


def check_night_exit(events: list[dict]) -> list[dict]:
    alerts = []

    for i in range(len(events) - 2):
        e1, e2, e3 = events[i], events[i + 1], events[i + 2]
        t1 = parse_time(e1)

        if not is_between(t1, time(0, 0), time(5, 0)):
            continue

        if (
            event_is(e1, "entrance_door", "open")
            and event_is(e2, "floor_mat", "pressed")
            and event_is(e3, "entrance_door", "closed")
        ):
            alerts.append(make_alert(
                "exit_appartment_at_night",
                event_time_text(e1),
                "Resident appears to exit the apartment during night hours.",
                [
                    f"Entrance door opened at {event_time_text(e1)}.",
                    f"Entrance pressure mat was pressed at {event_time_text(e2)}.",
                    f"Entrance door closed at {event_time_text(e3)}."
                ],
                "Notify the caregiver immediately."
            ))

    return alerts


def check_door_open_at_night(events: list[dict]) -> list[dict]:
    alerts = []
    open_event = None

    for e in events:
        t = parse_time(e)

        if event_is(e, "entrance_door", "open") and is_between(t, time(0, 0), time(5, 0)):
            open_event = e

        elif event_is(e, "entrance_door", "closed") and open_event:
            duration = parse_time(e) - parse_time(open_event)

            if duration > timedelta(minutes=30):
                alerts.append(make_alert(
                    "door_open_at_night",
                    event_time_text(e),
                    "Entrance door remained open at night for more than 30 minutes.",
                    [
                        f"Entrance door opened at {event_time_text(open_event)}.",
                        f"Entrance door closed at {event_time_text(e)}.",
                        f"Open duration was approximately {int(duration.total_seconds() / 60)} minutes."
                    ],
                    "Notify the caregiver immediately."
                ))

            open_event = None

    if open_event:
        alerts.append(make_alert(
            "door_open_at_night",
            event_time_text(open_event),
            "Entrance door opened at night and no closing event was found in the available data.",
            [
                f"Entrance door opened at {event_time_text(open_event)}.",
                "No entrance door closed event appears after it in the available window."
            ],
            "Check the entrance door immediately."
        ))

    return alerts


def check_door_open_while_sleeping(events: list[dict]) -> list[dict]:
    alerts = []
    door_open_event = None
    already_alerted = False

    for e in events:
        if event_is(e, "entrance_door", "open"):
            door_open_event = e
            already_alerted = False

        elif event_is(e, "entrance_door", "closed"):
            door_open_event = None
            already_alerted = False

        if door_open_event and not already_alerted and event_is(e, "pressure_bed_bedroom", "occupied"):
            alerts.append(make_alert(
                "door_open_while_sleeping",
                event_time_text(e),
                "Entrance door appears open while resident is in bed.",
                [
                    f"Entrance door opened at {event_time_text(door_open_event)}.",
                    f"Bed pressure became occupied at {event_time_text(e)}.",
                    "No entrance door closed event was observed before bed occupancy."
                ],
                "Notify the caregiver immediately."
            ))
            already_alerted = True

    return alerts


def check_water_running_no_bathroom(events: list[dict]) -> list[dict]:
    alerts = []

    bathroom_motion_times = [
        parse_time(e)
        for e in events
        if event_is(e, "pir_bathroom", "detected")
    ]

    for e in events:
        if e.get("sensor_id", "").startswith("waterflow_") and e.get("state") == "active":
            event_time = parse_time(e)

            nearby_motion = any(
                abs((event_time - motion_time).total_seconds()) <= 300
                for motion_time in bathroom_motion_times
            )

            if not nearby_motion:
                alerts.append(make_alert(
                    "water_running_no_bathroom",
                    event_time_text(e),
                    "Water activity detected without nearby bathroom presence.",
                    [
                        f"Waterflow sensor active at {event_time_text(e)}.",
                        "No bathroom PIR motion was detected within 5 minutes."
                    ],
                    "Ask the resident or caregiver to check whether water was left running."
                ))

    return alerts


def check_long_sedentary_period(events: list[dict]) -> list[dict]:
    alerts = []
    sitting_event = None
    activity_locations = {"Kitchen", "Bathroom"}

    sitting_sensor_ids = {
        "couch_pressure_living_room",
        "pressure_sofa_livingroom",
        "chair_pressure_living_room",
        "armchair_pressure_living_room",
    }

    for e in events:
        if e.get("sensor_id") in sitting_sensor_ids and e.get("state") == "occupied":
            sitting_event = e

        elif e.get("sensor_id") in sitting_sensor_ids and e.get("state") == "empty":
            if sitting_event:
                duration = parse_time(e) - parse_time(sitting_event)

                activity_between = any(
                    parse_time(sitting_event) < parse_time(x) < parse_time(e)
                    and x.get("location") in activity_locations
                    for x in events
                )

                if duration >= timedelta(minutes=60) and not activity_between:
                    alerts.append(make_alert(
                        "long_sedentary_period",
                        event_time_text(e),
                        "Resident appears to remain seated for 60+ minutes without kitchen or bathroom activity.",
                        [
                            f"Sitting started at {event_time_text(sitting_event)}.",
                            f"Sitting ended at {event_time_text(e)}.",
                            "No kitchen or bathroom activity was detected during this period."
                        ],
                        "Caregiver may check whether the resident is comfortable and responsive."
                    ))

            sitting_event = None

    return alerts


def check_late_wakeup(events: list[dict]) -> list[dict]:
    alerts = []

    bed_occupied_0730 = False
    bed_empty_before_0830 = False
    same_day = None

    for e in events:
        dt = parse_time(e)
        same_day = dt.date()

        if event_is(e, "pressure_bed_bedroom", "occupied") and dt.time() <= time(7, 30):
            bed_occupied_0730 = True

        if event_is(e, "pressure_bed_bedroom", "empty") and time(7, 30) <= dt.time() <= time(8, 30):
            bed_empty_before_0830 = True

    if bed_occupied_0730 and not bed_empty_before_0830 and same_day:
        alerts.append(make_alert(
            "late_wakeup",
            f"{same_day}T08:30:00",
            "Resident still appears to be in bed during the late wake-up window.",
            [
                "Bed pressure indicated occupancy around or before 07:30.",
                "No bed empty event was detected between 07:30 and 08:30."
            ],
            "Check later data or ask the caregiver to verify if the resident woke up late."
        ))

    return alerts


def check_late_medication(events: list[dict]) -> list[dict]:
    alerts = []

    if not events:
        return alerts

    day = parse_time(events[0]).date()

    medicine_seen = any(
        event_is(e, "medicine_cabinet", "detected")
        and time(8, 30) <= parse_time(e).time() <= time(9, 30)
        for e in events
    )

    has_window_context = any(
        time(8, 30) <= parse_time(e).time() <= time(9, 30)
        for e in events
    )

    if has_window_context and not medicine_seen:
        alerts.append(make_alert(
            "late_medication",
            f"{day}T09:30:00",
            "No medicine cabinet activity was detected during the late medication window.",
            [
                "The expected medication window was 08:30 to 09:30.",
                "No medicine_cabinet detected event appeared in the available data during that window."
            ],
            "Send a non-urgent reminder or ask the caregiver to verify medication."
        ))

    return alerts


def run_rules(events: list[dict]) -> list[dict]:
    events = sorted(events, key=parse_time)

    alerts = []
    alerts.extend(check_fridge_left_open(events))
    alerts.extend(check_stove_on_left_or_sleep(events))
    alerts.extend(check_night_exit(events))
    alerts.extend(check_door_open_at_night(events))
    alerts.extend(check_door_open_while_sleeping(events))
    alerts.extend(check_water_running_no_bathroom(events))
    alerts.extend(check_long_sedentary_period(events))
    alerts.extend(check_late_wakeup(events))
    alerts.extend(check_late_medication(events))

    return alerts


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Sensor data file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("sensor_data.json must contain a list of events.")

    return data


def main() -> None:
    events = load_events(SENSOR_DATA_PATH)
    alerts = run_rules(events)

    result = {
        "mode": "rule_engine",
        "summary": (
            f"{len(alerts)} alert(s) detected by deterministic rules."
            if alerts else
            "No rule-based alerts detected in the available data."
        ),
        "alerts": alerts
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, ensure_ascii=False)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nSaved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()