import json
from pathlib import Path

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "phi3:mini"

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


def load_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")

def call_ollama_json(system_prompt: str, user_prompt: str, timeout_seconds: int = 120) -> dict:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "num_predict": 220

        }
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout_seconds)

        if response.status_code >= 300:
            return {
                "mode": "llm_error",
                "summary": f"Ollama request failed with status {response.status_code}.",
                "alerts": [],
                "raw_output": response.text
            }

        content = response.json()["message"]["content"]

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "mode": "llm_error",
                "summary": "The model did not return valid JSON.",
                "alerts": [],
                "raw_output": content
            }

    except requests.RequestException as exc:
        return {
            "mode": "llm_error",
            "summary": f"Ollama request failed: {exc}",
            "alerts": [],
            "raw_output": ""
        }

def call_ollama_text(system_prompt: str, user_prompt: str, timeout_seconds: int = 300) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 250
        }
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout_seconds)

        if response.status_code >= 300:
            return f"Ollama request failed with status {response.status_code}: {response.text}"

        return response.json()["message"]["content"].strip()

    except requests.RequestException as exc:
        return f"Ollama request failed: {exc}"


def save_json(data, path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)