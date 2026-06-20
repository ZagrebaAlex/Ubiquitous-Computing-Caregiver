import json
from pathlib import Path

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "phi3:mini"

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

PROMPT_PATHS = [
    PROJECT_DIR / "LLM_Prompt.md",
    PROJECT_DIR / "LLM_Promt.md",
    BASE_DIR / "LLM_Prompt.md",
    BASE_DIR / "LLM_Promt.md",
]


def load_care_plan_prompt() -> str:
    for path in PROMPT_PATHS:
        if path.exists():
            return path.read_text(encoding="utf-8")

    raise FileNotFoundError("Could not find LLM_Prompt.md or LLM_Promt.md")


def call_ollama_json(system_prompt: str, user_prompt: str) -> dict:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
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
            "mode": "llm_error",
            "summary": "The model did not return valid JSON.",
            "alerts": [],
            "raw_output": content
        }


def save_json(data, path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)