import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta

from fetch_events import fetch_events, fetch_events_between, parse_datetime
from routine_auditor import run_routine_rules
from llm_client import call_ollama_text, save_json

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

DAILY_SENSOR_DATA_PATH = BASE_DIR / "sensor_data_24h.json"
DAILY_SUMMARY_PATH = BASE_DIR / "narrator_daily_summary.json"
ROUTINE_ALERTS_PATH = BASE_DIR / "narrator_routine_alerts.json"
DASHBOARD_24H_PATH = BASE_DIR / "dashboard_posts_24h.json"
LLM_NARRATOR_OUTPUT_PATH = BASE_DIR / "llm_narrator_output.json"

NARRATOR_PROMPT_PATHS = [
    PROJECT_DIR / "LLM_Narrator_Prompt.md",
    BASE_DIR / "LLM_Narrator_Prompt.md",
]


def load_narrator_prompt() -> str:
    for path in NARRATOR_PROMPT_PATHS:
        if path.exists():
            return path.read_text(encoding="utf-8")

    raise FileNotFoundError("Could not find LLM_Narrator_Prompt.md")


def load_json_file(path: Path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def compact_daily_summary(events: list[dict]) -> dict:
    summary = {
        "wake_up_times": [],
        "sleep_times": [],
        "medicine_times": [],
        "kitchen_activity_times": [],
        "fridge_activity": [],
        "stove_activity": [],
        "bathroom_presence_times": [],
        "toilet_activity": [],
        "sink_activity": [],
        "shower_activity": [],
        "balcony_activity": [],
        "entrance_door_activity": [],
        "sedentary_activity": [],
        "total_events_seen": len(events),
    }

    for event in events:
        sensor_id = event.get("sensor_id")
        timestamp = event.get("timestamp")
        state = event.get("state")

        if not timestamp:
            continue

        if sensor_id == "pressure_bed_bedroom" and state == "empty":
            summary["wake_up_times"].append(timestamp)

        elif sensor_id == "pressure_bed_bedroom" and state == "occupied":
            summary["sleep_times"].append(timestamp)

        elif sensor_id == "medicine_cabinet":
            summary["medicine_times"].append(timestamp)

        elif sensor_id == "pir_kitchen":
            summary["kitchen_activity_times"].append(timestamp)

        elif sensor_id == "fridge_contact":
            summary["fridge_activity"].append(f"{timestamp} {state}")

        elif sensor_id == "stove_power":
            summary["stove_activity"].append(f"{timestamp} {state}")

        elif sensor_id == "pir_bathroom":
            summary["bathroom_presence_times"].append(timestamp)

        elif sensor_id == "waterflow_toilet":
            summary["toilet_activity"].append(f"{timestamp} {state}")

        elif sensor_id == "waterflow_sink":
            summary["sink_activity"].append(f"{timestamp} {state}")

        elif sensor_id == "waterflow_bathtub":
            summary["shower_activity"].append(f"{timestamp} {state}")

        elif sensor_id in ["pir_balcony", "door_balcony_livingroom", "door_balcony_bedroom"]:
            summary["balcony_activity"].append(f"{timestamp} {sensor_id} {state}")

        elif sensor_id == "entrance_door":
            summary["entrance_door_activity"].append(f"{timestamp} {state}")

        elif sensor_id in ["pressure_sofa_livingroom", "couch_pressure_living_room"]:
            summary["sedentary_activity"].append(f"{timestamp} {sensor_id} {state}")

    return summary


def build_narrator_prompt(question: str, daily_summary: dict, dashboard_posts: dict, routine_alerts: dict) -> str:
    return f"""
Caregiver question:
{question}

IMPORTANT:
The Safety Auditor dashboard alerts below are confirmed system alerts.
You must mention every alert in dashboard_posts.posts.
If any alert has severity "critical", clearly state that a critical safety alert occurred and include the time it occurred.
Never say there were no safety concerns if dashboard_posts.posts is not empty.

Don't post the events as is, reply in human language, in sentences, explain what the data shows followed up with, as shown
by the sensor activity at x time.

Compact daily activity summary:
{json.dumps(daily_summary, indent=2, ensure_ascii=False)}

Existing dashboard alerts from Safety Auditor:
{json.dumps(dashboard_posts, indent=2, ensure_ascii=False)}

Routine auditor output:
{json.dumps(routine_alerts, indent=2, ensure_ascii=False)}
"""


def main():
    parser = argparse.ArgumentParser(description="Narrator for caregiver questions.")
    parser.add_argument(
        "--question",
        type=str,
        default="What did my mother do today?"
    )
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--hours", type=int, default=24)

    args = parser.parse_args()

    if args.date:
        start_dt = datetime.fromisoformat(args.date)
        end_dt = start_dt + timedelta(days=1)
        sensor_data = fetch_events_between(start_dt, end_dt)

    elif args.start and args.end:
        sensor_data = fetch_events_between(
            parse_datetime(args.start),
            parse_datetime(args.end)
        )

    else:
        sensor_data = fetch_events(lookback_hours=args.hours)

    save_json(sensor_data, DAILY_SENSOR_DATA_PATH)

    daily_summary = compact_daily_summary(sensor_data)
    save_json(daily_summary, DAILY_SUMMARY_PATH)

    routine_alert_list = run_routine_rules(sensor_data)
    routine_alerts = {
        "mode": "routine_auditor",
        "events_checked": len(sensor_data),
        "summary": (
            f"{len(routine_alert_list)} routine alert(s) detected."
            if routine_alert_list
            else "No routine-level concerns detected."
        ),
        "alerts": routine_alert_list
    }
    save_json(routine_alerts, ROUTINE_ALERTS_PATH)

    dashboard_posts = load_json_file(DASHBOARD_24H_PATH, {"posts": []})

    system_prompt = load_narrator_prompt()
    user_prompt = build_narrator_prompt(
        question=args.question,
        daily_summary=daily_summary,
        dashboard_posts=dashboard_posts,
        routine_alerts=routine_alerts
    )

    answer = call_ollama_text(system_prompt, user_prompt, timeout_seconds=300)
    llm_output = {
        "mode": "narrator",
        "question": args.question,
        "answer": answer
    }

    save_json(llm_output, LLM_NARRATOR_OUTPUT_PATH)
    print(answer)

    print(f"24h sensor data saved to: {DAILY_SENSOR_DATA_PATH}")
    print(f"Compact daily summary saved to: {DAILY_SUMMARY_PATH}")
    print(f"Routine alerts saved to: {ROUTINE_ALERTS_PATH}")
    print(f"Narrator output saved to: {LLM_NARRATOR_OUTPUT_PATH}")


if __name__ == "__main__":
    main()