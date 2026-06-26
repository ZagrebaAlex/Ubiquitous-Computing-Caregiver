import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta

from fetch_events import fetch_events, fetch_events_between
from routine_auditor import run_routine_rules
from llm_client import call_ollama_text, save_json

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

DAILY_SENSOR_DATA_PATH = BASE_DIR / "sensor_data_24h.json"
DAILY_SUMMARY_PATH = BASE_DIR / "narrator_daily_summary.json"
ROUTINE_ALERTS_PATH = BASE_DIR / "narrator_routine_alerts.json"
DASHBOARD_24H_PATH = BASE_DIR / "dashboard_posts_24h.json"
LLM_NARRATOR_OUTPUT_PATH = BASE_DIR / "llm_narrator_output.json"

NARRATOR_PROMPT_PATH = PROJECT_DIR / "LLM_Narrator_Prompt.md"


def load_narrator_prompt() -> str:
    if not NARRATOR_PROMPT_PATH.exists():
        raise FileNotFoundError(f"Could not find narrator prompt: {NARRATOR_PROMPT_PATH}")

    return NARRATOR_PROMPT_PATH.read_text(encoding="utf-8")


def load_json_file(path: Path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def compact_daily_summary(events: list[dict]) -> dict:
    full_summary = {
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
            full_summary["wake_up_times"].append(timestamp)

        elif sensor_id == "pressure_bed_bedroom" and state == "occupied":
            full_summary["sleep_times"].append(timestamp)

        elif sensor_id == "medicine_cabinet":
            full_summary["medicine_times"].append(timestamp)

        elif sensor_id == "pir_kitchen":
            full_summary["kitchen_activity_times"].append(timestamp)

        elif sensor_id == "fridge_contact":
            full_summary["fridge_activity"].append(f"{timestamp} {state}")

        elif sensor_id == "stove_power":
            full_summary["stove_activity"].append(f"{timestamp} {state}")

        elif sensor_id == "pir_bathroom":
            full_summary["bathroom_presence_times"].append(timestamp)

        elif sensor_id == "waterflow_toilet":
            full_summary["toilet_activity"].append(f"{timestamp} {state}")

        elif sensor_id == "waterflow_sink":
            full_summary["sink_activity"].append(f"{timestamp} {state}")

        elif sensor_id == "waterflow_bathtub":
            full_summary["shower_activity"].append(f"{timestamp} {state}")

        elif sensor_id in ["pir_balcony", "door_balcony_livingroom", "door_balcony_bedroom"]:
            full_summary["balcony_activity"].append(f"{timestamp} {sensor_id} {state}")

        elif sensor_id == "entrance_door":
            full_summary["entrance_door_activity"].append(f"{timestamp} {state}")

        elif sensor_id in ["pressure_sofa_livingroom", "couch_pressure_living_room"]:
            full_summary["sedentary_activity"].append(f"{timestamp} {sensor_id} {state}")

    compact_summary = {
        "wake_up_times": full_summary["wake_up_times"][:3],
        "sleep_times": full_summary["sleep_times"][:3],
        "medicine_times": full_summary["medicine_times"][:3],
        "kitchen_activity_count": len(full_summary["kitchen_activity_times"]),
        "fridge_activity": full_summary["fridge_activity"][:6],
        "stove_activity": full_summary["stove_activity"][:6],
        "bathroom_presence_count": len(full_summary["bathroom_presence_times"]),
        "toilet_activity": full_summary["toilet_activity"][:4],
        "sink_activity": full_summary["sink_activity"][:4],
        "shower_activity": full_summary["shower_activity"][:4],
        "balcony_activity": full_summary["balcony_activity"][:4],
        "entrance_door_activity": full_summary["entrance_door_activity"][:4],
        "sedentary_activity": full_summary["sedentary_activity"][:4],
        "total_events_seen": full_summary["total_events_seen"],
    }

    return compact_summary


def build_narrator_prompt(
    question: str,
    daily_summary: dict,
    dashboard_posts: dict,
    routine_alerts: dict
) -> str:
    return f"""
Caregiver question:
{question}

Reply in natural human language based on the daily activity summary

Mention confirmed Safety Auditor alerts if any exist.
If any confirmed alert has severity "critical", clearly say that a critical safety alert occurred and include the time.

Here is the data from today

Daily activity summary:
{json.dumps(daily_summary, indent=2, ensure_ascii=False)}

Confirmed Safety Auditor alerts:
{json.dumps(dashboard_posts, indent=2, ensure_ascii=False)}

Routine auditor output:
{json.dumps(routine_alerts, indent=2, ensure_ascii=False)}
"""


def run_narrator(question: str, date: str | None = None) -> dict:
    if date:
        start_dt = datetime.fromisoformat(date)
        end_dt = start_dt + timedelta(days=1)
        sensor_data = fetch_events_between(start_dt, end_dt)
    else:
        sensor_data = fetch_events(lookback_hours=24)

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
        question=question,
        daily_summary=daily_summary,
        dashboard_posts=dashboard_posts,
        routine_alerts=routine_alerts
    )

    answer = call_ollama_text(system_prompt, user_prompt, timeout_seconds=300)

    result = {
        "mode": "narrator",
        "answer": answer,
        "confidence": "medium",
        "reason": "Answer generated from compact 24h activity summary, dashboard alerts, and routine-auditor context.",
        "alerts": dashboard_posts.get("posts", [])
    }

    save_json(result, LLM_NARRATOR_OUTPUT_PATH)
    return result


def main():
    parser = argparse.ArgumentParser(description="Narrator for caregiver questions.")
    parser.add_argument("--question", type=str, default="What did my mother do today?")
    parser.add_argument("--date", type=str, default=None)

    args = parser.parse_args()

    result = run_narrator(
        question=args.question,
        date=args.date
    )

    print(result["answer"])
    print()
    print(f"Narrator output saved to: {LLM_NARRATOR_OUTPUT_PATH}")


if __name__ == "__main__":
    main()