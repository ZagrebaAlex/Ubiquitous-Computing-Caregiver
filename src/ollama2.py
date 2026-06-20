# src/ollama2.py

import argparse
import json
from pathlib import Path
from datetime import datetime

import requests


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "phi3:mini"

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

SENSOR_DATA_PATH = BASE_DIR / "sensor_data.json"
PROMPT_PATH = PROJECT_DIR / "LLM_Prompt.md"

ALERT_OUTPUT_PATH = BASE_DIR / "llm_hourly_alert.json"
NARRATOR_OUTPUT_PATH = BASE_DIR / "llm_narrator_response.json"


def load_text_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path.resolve()}")
    return path.read_text(encoding="utf-8")


def load_json_file(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path.resolve()}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json_file(data, path: Path):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def call_ollama(system_prompt: str, user_prompt: str):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
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


def run_safety_auditor(sensor_data):
    system_prompt = load_text_file(PROMPT_PATH)

    user_prompt = f"""
Mode: Safety Auditor Mode

You are receiving the last 1 hour of raw sensor telemetry.
Only create alerts for issues that can be proven from this data window.

Return the required Safety Auditor JSON structure.

Sensor data:
{json.dumps(sensor_data, indent=2, ensure_ascii=False)}
"""

    return call_ollama(system_prompt, user_prompt)


def run_narrator(sensor_data, question: str):
    system_prompt = load_text_file(PROMPT_PATH)

    user_prompt = f"""
Mode: Narrator Mode

Caregiver question:
{question}

Answer using only the available sensor data.

Recent sensor data:
{json.dumps(sensor_data, indent=2, ensure_ascii=False)}
"""

    return call_ollama(system_prompt, user_prompt)


def main():
    parser = argparse.ArgumentParser(
        description="Invisible Caregiver LLM client using Ollama Phi-3 Mini"
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
        print("Sensor data:", SENSOR_DATA_PATH.resolve())
        print("Sensor data exists:", SENSOR_DATA_PATH.exists())
        print("Prompt:", PROMPT_PATH.resolve())
        print("Prompt exists:", PROMPT_PATH.exists())

    sensor_data = load_json_file(SENSOR_DATA_PATH)

    if args.mode == "safety":
        result = run_safety_auditor(sensor_data)
        save_json_file(result, ALERT_OUTPUT_PATH)
        print(f"Safety alert JSON saved to: {ALERT_OUTPUT_PATH.resolve()}")

    else:
        result = run_narrator(sensor_data, args.question)
        save_json_file(result, NARRATOR_OUTPUT_PATH)
        print(f"Narrator JSON saved to: {NARRATOR_OUTPUT_PATH.resolve()}")

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()