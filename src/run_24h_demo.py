import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

from house_sim import make_sensor_event, send_events

BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_24H_PATH = BASE_DIR / "dashboard_posts_24h.json"


def hour_start(base_day, hour):
    return base_day.replace(hour=hour, minute=0, second=0, microsecond=0)


def normal_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=10), "pir_living_room", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=35), "pir_kitchen", "motion", "detected", 1),
    ]


def morning_routine(base):
    return [
        make_sensor_event(base + timedelta(minutes=5), "pressure_bed_bedroom", "pressure", "empty", 0),
        make_sensor_event(base + timedelta(minutes=10), "pir_bathroom", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=13), "waterflow_toilet", "waterflow", "active", 1),
        make_sensor_event(base + timedelta(minutes=14), "waterflow_toilet", "waterflow", "inactive", 0),
        make_sensor_event(base + timedelta(minutes=16), "waterflow_sink", "waterflow", "active", 1),
        make_sensor_event(base + timedelta(minutes=17), "waterflow_sink", "waterflow", "inactive", 0),
    ]

def breakfast_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=5), "pir_kitchen", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=8), "fridge_contact", "contact", "open", 1),
        make_sensor_event(base + timedelta(minutes=11), "fridge_contact", "contact", "closed", 0),
        make_sensor_event(base + timedelta(minutes=15), "stove_power", "power", "on", 1),
        make_sensor_event(base + timedelta(minutes=25), "medicine_cabinet", "vibration", "detected", 1),
        make_sensor_event(base + timedelta(minutes=35), "stove_power", "power", "off", 0),
    ]


def meal_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=5), "pir_kitchen", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=8), "fridge_contact", "contact", "open", 1),
        make_sensor_event(base + timedelta(minutes=11), "fridge_contact", "contact", "closed", 0),
        make_sensor_event(base + timedelta(minutes=15), "stove_power", "power", "on", 1),
        make_sensor_event(base + timedelta(minutes=35), "stove_power", "power", "off", 0),
    ]


def shower_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=5), "pir_bathroom", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=8), "waterflow_bathtub", "waterflow", "active", 1),
        make_sensor_event(base + timedelta(minutes=20), "waterflow_bathtub", "waterflow", "inactive", 0),
    ]


def balcony_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=5), "door_balcony_livingroom", "contact", "open", 1),
        make_sensor_event(base + timedelta(minutes=10), "pir_balcony", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=30), "pir_balcony", "motion", "not_detected", 0),
        make_sensor_event(base + timedelta(minutes=50), "door_balcony_livingroom", "contact", "closed", 0),
    ]


def sleep_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=15), "pressure_bed_bedroom", "pressure", "occupied", 1),
    ]


def decline_fridge_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=5), "pir_kitchen", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=8), "fridge_contact", "contact", "open", 1),
        make_sensor_event(base + timedelta(minutes=25), "fridge_contact", "contact", "closed", 0),
    ]


def decline_sedentary_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=0), "couch_pressure_living_room", "pressure", "occupied", 1),
        make_sensor_event(base + timedelta(minutes=59), "couch_pressure_living_room", "pressure", "empty", 0),
    ]


def hazard_stove_sleep_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=5), "stove_power", "power", "on", 1),
        make_sensor_event(base + timedelta(minutes=12), "pir_bedroom", "motion", "detected", 1),
        make_sensor_event(base + timedelta(minutes=15), "pressure_bed_bedroom", "pressure", "occupied", 1),
    ]


def hazard_night_exit_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=0), "entrance_door", "contact", "open", 1),
        make_sensor_event(base + timedelta(minutes=1), "floor_mat", "pressure", "pressed", 1),
        make_sensor_event(base + timedelta(minutes=2), "entrance_door", "contact", "closed", 0),
    ]


def hazard_door_open_night_hour(base):
    return [
        make_sensor_event(base + timedelta(minutes=0), "entrance_door", "contact", "open", 1),
        make_sensor_event(base + timedelta(minutes=40), "entrance_door", "contact", "closed", 0),
    ]


def build_normal_day_hour(base_day, hour):
    base = hour_start(base_day, hour)

    if hour == 7:
        return morning_routine(base)
    if hour == 8:
        return breakfast_hour(base)
    if hour in [13, 18]:
        return meal_hour(base)
    if hour == 19:
        return balcony_hour(base)
    if hour == 20:
        return shower_hour(base)
    if hour == 23:
        return sleep_hour(base)

    return normal_hour(base)


def build_decline_day_hour(base_day, hour):
    base = hour_start(base_day, hour)

    if hour == 13:
        return decline_fridge_hour(base)
    if hour == 15:
        return decline_sedentary_hour(base)

    return build_normal_day_hour(base_day, hour)


def build_hazard_day_hour(base_day, hour):
    base = hour_start(base_day, hour)

    if hour == 3:
        return hazard_night_exit_hour(base)
    if hour == 22:
        return hazard_stove_sleep_hour(base)

    return build_normal_day_hour(base_day, hour)


def build_events_for_hour(base_day, hour, scenario):
    if scenario == "normal":
        return build_normal_day_hour(base_day, hour)

    if scenario == "decline":
        return build_decline_day_hour(base_day, hour)

    if scenario == "hazard":
        return build_hazard_day_hour(base_day, hour)

    raise ValueError(f"Unknown scenario: {scenario}")


def reset_dashboard_24h():
    with DASHBOARD_24H_PATH.open("w", encoding="utf-8") as file:
        json.dump({"posts": []}, file, indent=2, ensure_ascii=False)


def run_safety_auditor(start_dt, end_dt):
    subprocess.run(
        [
            "python",
            "safety_auditor.py",
            "--start",
            start_dt.isoformat(timespec="seconds"),
            "--end",
            end_dt.isoformat(timespec="seconds"),
        ],
        cwd=BASE_DIR,
        check=True
    )


def main():
    parser = argparse.ArgumentParser(description="Run a 24h simulated day through ThingsBoard and Safety Auditor.")
    parser.add_argument(
        "--scenario",
        choices=["normal", "decline", "hazard"],
        required=True
    )
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d")
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0,
        help="Optional pause after each hourly audit. Default: 0."
    )

    args = parser.parse_args()

    base_day = datetime.fromisoformat(args.date)
    reset_dashboard_24h()

    for hour in range(24):
        start_dt = hour_start(base_day, hour)
        end_dt = start_dt + timedelta(hours=1)

        print()
        print(f"=== {args.scenario.upper()} | {start_dt} -> {end_dt} ===")

        events = build_events_for_hour(base_day, hour, args.scenario)
        send_events(events)

        print(f"Sent {len(events)} events.")
        print("Running safety auditor...")

        run_safety_auditor(start_dt, end_dt)

        if args.sleep > 0:
            import time
            time.sleep(args.sleep)

    print()
    print("24h simulation completed.")
    print(f"Compact dashboard alert history saved to: {DASHBOARD_24H_PATH}")


if __name__ == "__main__":
    main()