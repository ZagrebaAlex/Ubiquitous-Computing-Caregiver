import argparse
import json
from pathlib import Path

from fetch_events import fetch_events
from routine_auditor import run_routine_rules
from llm_client import load_care_plan_prompt, call_ollama_json, save_json

BASE_DIR = Path(__file__).resolve().parent

DAILY_SENSOR_DATA_PATH = BASE_DIR / "sensor_data_24h.json"
ROUTINE_ALERTS_PATH = BASE_DIR / "narrator_routine_alerts.json"
LLM_NARRATOR_OUTPUT_PATH = BASE_DIR / "llm_narrator_output.json"


def build_narrator_prompt(
    sensor_data: list[dict],
    routine_alerts: dict,
    question: str
) -> str:
    return f"""
Mode: Narrator Mode

Caregiver question:
{question}

You are receiving:
1. The last 24 hours of sensor telemetry.
2. Routine/risk classifications from the Python rule engine.

The rule engine is the source of truth for alert classification.
Do not invent new alerts.
Do not send email or SMS.
Do not create dashboard posts.
Only answer the caregiver question in human language.

Return valid JSON only.

Required output format:

{{
  "mode": "narrator",
  "answer": "Warm, factual answer to the caregiver.",
  "confidence": "high | medium | low",
  "reason": "Short explanation of what evidence supports the answer.",
  "alerts": []
}}

Last 24 hours sensor data:
{json.dumps(sensor_data, indent=2, ensure_ascii=False)}

Routine rule engine output:
{json.dumps(routine_alerts, indent=2, ensure_ascii=False)}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Narrator using last 24h ThingsBoard data")
    parser.add_argument(
        "--question",
        type=str,
        default="What did my mother do today?"
    )
    args = parser.parse_args()

    sensor_data = fetch_events(lookback_hours=24)
    save_json(sensor_data, DAILY_SENSOR_DATA_PATH)

    alerts = run_routine_rules(sensor_data)

    routine_alerts = {
        "mode": "routine_auditor",
        "window_hours": 24,
        "events_checked": len(sensor_data),
        "summary": (
            f"{len(alerts)} routine alert(s) detected."
            if alerts else
            "No routine-level concerns detected."
        ),
        "alerts": alerts
    }

    save_json(routine_alerts, ROUTINE_ALERTS_PATH)

    care_plan_prompt = load_care_plan_prompt()
    user_prompt = build_narrator_prompt(sensor_data, routine_alerts, args.question)

    llm_output = call_ollama_json(care_plan_prompt, user_prompt)
    save_json(llm_output, LLM_NARRATOR_OUTPUT_PATH)

    print(json.dumps(llm_output, indent=2, ensure_ascii=False))
    print()
    print(f"24h sensor data saved to: {DAILY_SENSOR_DATA_PATH}")
    print(f"Routine alerts saved to: {ROUTINE_ALERTS_PATH}")
    print(f"Narrator output saved to: {LLM_NARRATOR_OUTPUT_PATH}")


if __name__ == "__main__":
    main()