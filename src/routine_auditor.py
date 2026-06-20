import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta, time

from fetch_events import fetch_events
from rule_alerts import (
    parse_time,
    event_is,
    event_time_text,
    make_alert,
)

BASE_DIR = Path(__file__).resolve().parent

ROUTINE_WINDOW_PATH = BASE_DIR / "sensor_data_daily.json"
ROUTINE_ALERTS_PATH = BASE_DIR / "routine_alerts.json"


def load_events(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("Input JSON must contain a list of sensor events.")

    return data


def save_json(data, path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def date_at(day, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour=hour, minute=minute))


def events_after(events: list[dict], dt: datetime) -> bool:
    return any(parse_time(event) >= dt for event in events)


def has_event_between(
    events: list[dict],
    start: datetime,
    end: datetime,
    sensor_id: str | None = None,
    state: str | None = None,
    sensor_ids: set[str] | None = None,
) -> bool:
    for event in events:
        event_dt = parse_time(event)

        if not (start <= event_dt <= end):
            continue

        if sensor_id is not None and event.get("sensor_id") != sensor_id:
            continue

        if sensor_ids is not None and event.get("sensor_id") not in sensor_ids:
            continue

        if state is not None and event.get("state") != state:
            continue

        return True

    return False


def first_event_between(
    events: list[dict],
    start: datetime,
    end: datetime,
    sensor_id: str | None = None,
    state: str | None = None,
    sensor_ids: set[str] | None = None,
) -> dict | None:
    matching = []

    for event in events:
        event_dt = parse_time(event)

        if not (start <= event_dt <= end):
            continue

        if sensor_id is not None and event.get("sensor_id") != sensor_id:
            continue

        if sensor_ids is not None and event.get("sensor_id") not in sensor_ids:
            continue

        if state is not None and event.get("state") != state:
            continue

        matching.append(event)

    if not matching:
        return None

    return sorted(matching, key=parse_time)[0]


def check_wakeup_routine(events: list[dict]) -> list[dict]:
    alerts = []

    if not events:
        return alerts

    days = sorted({parse_time(event).date() for event in events})

    for day in days:
        morning_start = date_at(day, 4, 0)
        late_limit = date_at(day, 7, 30)
        very_late_limit = date_at(day, 8, 30)
        morning_end = date_at(day, 12, 0)

        wake_event = first_event_between(
            events,
            morning_start,
            morning_end,
            sensor_id="pressure_bed_bedroom",
            state="empty"
        )

        if wake_event is None and events_after(events, very_late_limit):
            alerts.append(make_alert(
                "very_late_wakeup",
                f"{day}T08:30:00",
                "No bed-empty event was detected during the morning wake-up period.",
                [
                    "Expected wake-up was around 07:00.",
                    "No pressure_bed_bedroom empty event appeared by 08:30."
                ],
                "Caregiver may check whether the resident woke up unusually late."
            ))
            continue

        if wake_event:
            wake_time = parse_time(wake_event)

            if wake_time > very_late_limit:
                alerts.append(make_alert(
                    "very_late_wakeup",
                    event_time_text(wake_event),
                    "Resident appears to have woken up very late.",
                    [
                        f"Bed became empty at {event_time_text(wake_event)}.",
                        "Expected wake-up was around 07:00, with significant concern after 08:30."
                    ],
                    "Caregiver may check whether the resident woke up unusually late."
                ))

            elif wake_time > late_limit:
                alerts.append(make_alert(
                    "late_wakeup",
                    event_time_text(wake_event),
                    "Resident appears to have woken up later than the normal routine.",
                    [
                        f"Bed became empty at {event_time_text(wake_event)}.",
                        "Expected wake-up was around 07:00, with allowed delay until 07:30."
                    ],
                    "Record as a minor routine deviation."
                ))

    return alerts


def check_medication_routine(events: list[dict]) -> list[dict]:
    alerts = []

    if not events:
        return alerts

    days = sorted({parse_time(event).date() for event in events})

    for day in days:
        expected = date_at(day, 8, 0)
        late_limit = date_at(day, 8, 30)
        very_late_limit = date_at(day, 9, 30)
        daily_end = date_at(day, 23, 59)

        med_event = first_event_between(
            events,
            expected - timedelta(hours=1),
            daily_end,
            sensor_id="medicine_cabinet",
            state="detected"
        )

        if med_event is None and events_after(events, very_late_limit):
            alerts.append(make_alert(
                "very_late_medication",
                f"{day}T09:30:00",
                "No medicine cabinet activity was detected after the expected medication time.",
                [
                    "Expected medication was around 08:00.",
                    "No medicine_cabinet detected event appeared by 09:30."
                ],
                "Ask the caregiver to verify whether medication was taken."
            ))
            continue

        if med_event:
            med_time = parse_time(med_event)

            if med_time > very_late_limit:
                alerts.append(make_alert(
                    "very_late_medication",
                    event_time_text(med_event),
                    "Medication activity appears very late.",
                    [
                        f"Medicine cabinet activity was detected at {event_time_text(med_event)}.",
                        "Expected medication was around 08:00, with concern after 09:30."
                    ],
                    "Ask the caregiver to verify medication."
                ))

            elif med_time > late_limit:
                alerts.append(make_alert(
                    "late_medication",
                    event_time_text(med_event),
                    "Medication activity appears later than the normal routine.",
                    [
                        f"Medicine cabinet activity was detected at {event_time_text(med_event)}.",
                        "Expected medication was around 08:00, with allowed delay until 08:30."
                    ],
                    "Send a non-urgent reminder or record as a minor routine deviation."
                ))

    return alerts


def check_meal_routine(events: list[dict]) -> list[dict]:
    alerts = []

    meal_sensors = {
        "fridge_contact",
        "stove_power",
        "toaster_power",
    }

    meals = [
        ("breakfast", 8, 40),
        ("lunch", 13, 0),
        ("dinner", 18, 0),
    ]

    if not events:
        return alerts

    days = sorted({parse_time(event).date() for event in events})

    for day in days:
        for meal_name, hour, minute in meals:
            expected = date_at(day, hour, minute)
            allowed_until = expected + timedelta(hours=1)
            missed_until = expected + timedelta(hours=2)

            meal_seen_by_allowed = has_event_between(
                events,
                expected - timedelta(minutes=30),
                allowed_until,
                sensor_ids=meal_sensors
            )

            meal_seen_by_missed = has_event_between(
                events,
                expected - timedelta(minutes=30),
                missed_until,
                sensor_ids=meal_sensors
            )

            if not meal_seen_by_allowed and meal_seen_by_missed:
                alerts.append(make_alert(
                    "delayed_meal_activity",
                    allowed_until.strftime("%Y-%m-%dT%H:%M:%S"),
                    f"{meal_name.capitalize()} activity appears delayed.",
                    [
                        f"Expected {meal_name} around {expected.strftime('%H:%M')}.",
                        "No meal-related activity was detected within the allowed 1-hour delay.",
                        "Meal-related activity appeared later within the wider 2-hour window."
                    ],
                    "Record as a minor routine deviation."
                ))

            elif not meal_seen_by_missed and events_after(events, missed_until):
                alerts.append(make_alert(
                    "missed_meal_window",
                    missed_until.strftime("%Y-%m-%dT%H:%M:%S"),
                    f"No clear {meal_name} activity was detected within the expected meal window.",
                    [
                        f"Expected {meal_name} around {expected.strftime('%H:%M')}.",
                        "No fridge, stove, or toaster activity was detected within 2 hours."
                    ],
                    "Caregiver may check whether the resident skipped or delayed the meal."
                ))

    return alerts


def check_shower_routine(events: list[dict]) -> list[dict]:
    alerts = []

    if not events:
        return alerts

    days = sorted({parse_time(event).date() for event in events})

    for day in days:
        expected = date_at(day, 20, 0)
        delayed_until = date_at(day, 21, 0)
        daily_end = date_at(day, 23, 59)

        shower_seen = has_event_between(
            events,
            expected - timedelta(hours=2),
            delayed_until,
            sensor_id="waterflow_bathtub",
            state="active"
        )

        if not shower_seen and events_after(events, delayed_until):
            alerts.append(make_alert(
                "delayed_shower",
                delayed_until.strftime("%Y-%m-%dT%H:%M:%S"),
                "No shower-related water activity was detected around the expected shower time.",
                [
                    "Expected shower was around 20:00.",
                    "No waterflow_bathtub active event appeared by 21:00."
                ],
                "Record as a minor routine deviation."
            ))

    return alerts


def check_sleep_routine(events: list[dict]) -> list[dict]:
    alerts = []

    if not events:
        return alerts

    days = sorted({parse_time(event).date() for event in events})

    for day in days:
        expected = date_at(day, 23, 0)
        delayed_start = date_at(day, 23, 30)
        delayed_end = date_at(day + timedelta(days=1), 0, 30)

        sleep_seen = has_event_between(
            events,
            delayed_start,
            delayed_end,
            sensor_id="pressure_bed_bedroom",
            state="occupied"
        )

        if not sleep_seen and events_after(events, delayed_end):
            alerts.append(make_alert(
                "delayed_sleep",
                delayed_end.strftime("%Y-%m-%dT%H:%M:%S"),
                "No bed occupancy was detected during the expected sleep window.",
                [
                    "Expected sleep was around 23:00.",
                    "No pressure_bed_bedroom occupied event appeared between 23:30 and 00:30."
                ],
                "Record as a minor routine deviation."
            ))

    return alerts


def add_multiple_routine_deviations(alerts: list[dict]) -> list[dict]:
    low_alerts = [alert for alert in alerts if alert.get("severity") == "low"]

    if len(low_alerts) >= 2:
        alerts.append(make_alert(
            "multiple_routine_deviations",
            low_alerts[-1]["timestamp"],
            "Multiple minor routine deviations were detected in the available daily window.",
            [
                f"{len(low_alerts)} low-level routine deviations were detected.",
                "This may indicate a broader routine drift rather than a single isolated event."
            ],
            "Caregiver may review the daily summary and check whether the resident needs support."
        ))

    return alerts


def run_routine_rules(events: list[dict]) -> list[dict]:
    events = sorted(events, key=parse_time)

    alerts = []
    alerts.extend(check_wakeup_routine(events))
    alerts.extend(check_medication_routine(events))
    alerts.extend(check_meal_routine(events))
    alerts.extend(check_shower_routine(events))
    alerts.extend(check_sleep_routine(events))

    alerts = add_multiple_routine_deviations(alerts)

    return alerts


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Routine Auditor")
    parser.add_argument(
        "--from-file",
        type=str,
        default=None,
        help="Optional JSON file to use instead of fetching from ThingsBoard."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Lookback window in hours. Default: 24."
    )

    args = parser.parse_args()

    if args.from_file:
        events = load_events(Path(args.from_file))
    else:
        events = fetch_events(lookback_hours=args.hours)

    save_json(events, ROUTINE_WINDOW_PATH)

    alerts = run_routine_rules(events)

    result = {
        "mode": "routine_auditor",
        "window_hours": args.hours,
        "events_checked": len(events),
        "summary": (
            f"{len(alerts)} routine alert(s) detected."
            if alerts
            else "No routine-level concerns were detected in the available daily window."
        ),
        "alerts": alerts
    }

    save_json(result, ROUTINE_ALERTS_PATH)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nRoutine window saved to: {ROUTINE_WINDOW_PATH}")
    print(f"Routine alerts saved to: {ROUTINE_ALERTS_PATH}")


if __name__ == "__main__":
    main()