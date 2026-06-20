import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timedelta

import requests

from thingsboard_client import fetch_device_events


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "phi3:mini")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

PROMPT_PATH = PROJECT_DIR / "LLM_Prompt.md"

ALERT_OUTPUT_PATH = BASE_DIR / "llm_hourly_alert.json"
NARRATOR_OUTPUT_PATH = BASE_DIR / "llm_narrator_response.json"
DEBUG_DIR = BASE_DIR / "debug"


def load_text_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path.resolve()}")

    return path.read_text(encoding="utf-8")


def save_json_file(data, path: Path):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file,  ensure_ascii=False)


def save_text_file(text: str, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def format_timestamp(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def build_event_timeline(sensor_data: list[dict]) -> str:
    if not sensor_data:
        return "No sensor events were available."

    lines = []

    for event in sensor_data:
        ts = event.get("timestamp", "-")
        sensor_id = event.get("sensor_id", "-")
        location = event.get("location", "-")
        sensor_type = event.get("sensor_type", "-")
        state = event.get("state", "-")
        value = event.get("value", "-")
        lines.append(
            f"- {format_timestamp(ts)} | {sensor_id} | {sensor_type} | {location} | state={state} | value={value}"
        )

    return "\n".join(lines)


def build_sensor_semantics() -> str:
    return """
Sensor semantics:
- `pressure_bed_bedroom`: 1 means the bed is occupied, 0 means unoccupied.
- `waterflow_toilet`: activity suggests toilet use, but a single pulse is not enough to confirm a full bathroom routine.
- `waterflow_sink`: activity may indicate hand washing or sink use.
- `waterflow_bathtub`: activity may indicate shower or bath use.
- `medicine_cabinet`: vibration may indicate the cabinet was opened or handled, but it does not prove pill ingestion.
- `pir_*`: motion detected in that room only.
- `fridge_contact` and `stove_power`: kitchen activity, not meal completion.
""".strip()


def build_narrator_prompt(question: str, sensor_data: list[dict]) -> str:
    if sensor_data:
        start = min(event["timestamp"] for event in sensor_data if event.get("timestamp"))
        end = max(event["timestamp"] for event in sensor_data if event.get("timestamp"))
    else:
        start = end = "N/A"

    return f"""
Mode: Narrator Mode

Caregiver question:
{question}

Answer using only the available sensor data from ThingsBoard.
Do not infer medication intake, toilet use, sleep, meals, or being "safe" unless the evidence is direct.
If the data is ambiguous, say so plainly.
Use the required Narrator JSON structure.

Current time:
{datetime.now().isoformat()}

Data window:
{start} to {end}

{build_sensor_semantics()}

Event timeline:
{build_event_timeline(sensor_data)}
""".strip()


def call_ollama(system_prompt: str, user_prompt: str):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1
        }
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=180)
    response.raise_for_status()

    content = response.json()["message"]["content"]

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "mode": "error",
            "summary": "The model did not return valid JSON.",
            "alerts": [],
            "raw_output": content
        }


def maybe_dump_debug_payload(mode: str, system_prompt: str, user_prompt: str, enabled: bool):
    if not enabled:
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_path = DEBUG_DIR / f"{stamp}_{mode}_prompt.txt"
    save_text_file(
        "=== SYSTEM PROMPT ===\n"
        + system_prompt
        + "\n\n=== USER PROMPT ===\n"
        + user_prompt,
        debug_path,
    )
    print("Debug prompt saved to:", debug_path.resolve())


def run_safety_auditor(debug: bool = False):
    system_prompt = load_text_file(PROMPT_PATH)
    sensor_data = fetch_device_events(lookback_hours=1)

    user_prompt = f"""
Mode: Safety Auditor Mode

You are receiving the last 1 hour of raw sensor telemetry from ThingsBoard.
Only create alerts for issues that can be proven from this data window.
Do not evaluate daily routines.
Return the required Safety Auditor JSON structure.

Current time:
{datetime.now().isoformat()}

Data window:
{(datetime.now() - timedelta(hours=1)).isoformat()} to {datetime.now().isoformat()}

{build_sensor_semantics()}

Event timeline:
{build_event_timeline(sensor_data)}
"""

    maybe_dump_debug_payload("safety", system_prompt, user_prompt, debug)
    return call_ollama(system_prompt, user_prompt)


def run_narrator(question: str, debug: bool = False):
    system_prompt = load_text_file(PROMPT_PATH)
    sensor_data = fetch_device_events(lookback_hours=24)
    user_prompt = build_narrator_prompt(question, sensor_data)
    maybe_dump_debug_payload("narrator", system_prompt, user_prompt, debug)
    return call_ollama(system_prompt, user_prompt)


def main():
    parser = argparse.ArgumentParser(
        description="Invisible Caregiver LLM client using ThingsBoard and Ollama"
    )

    parser.add_argument(
        "--mode",
        choices=["safety", "narrator"],
        required=True
    )

    parser.add_argument(
        "--question",
        type=str,
        default="How was Mom's day today?"
    )

    parser.add_argument(
        "--debug",
        action="store_true"
    )

    args = parser.parse_args()

    if args.debug:
        print("Script:", Path(__file__).resolve())
        print("Prompt:", PROMPT_PATH.resolve())
        print("Prompt exists:", PROMPT_PATH.exists())
        print("Ollama URL:", OLLAMA_URL)
        print("Model:", MODEL_NAME)

    if args.mode == "safety":
        result = run_safety_auditor(debug=args.debug)
        save_json_file(result, ALERT_OUTPUT_PATH)
        print(f"Safety alert JSON saved to: {ALERT_OUTPUT_PATH.resolve()}")

    else:
        result = run_narrator(args.question, debug=args.debug)
        save_json_file(result, NARRATOR_OUTPUT_PATH)
        print(f"Narrator JSON saved to: {NARRATOR_OUTPUT_PATH.resolve()}")

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
