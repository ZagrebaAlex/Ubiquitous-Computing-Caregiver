import json
from pathlib import Path

from fetch_events import fetch_events
from rule_alerts import run_rules
from llm_client import load_care_plan_prompt, call_ollama_json, save_json

BASE_DIR = Path(__file__).resolve().parent

HOURLY_SENSOR_DATA_PATH = BASE_DIR / "sensor_data_hourly.json"
RULE_ALERTS_PATH = BASE_DIR / "safety_rule_alerts.json"
LLM_SAFETY_OUTPUT_PATH = BASE_DIR / "llm_safety_output.json"
DASHBOARD_POST_PATH = BASE_DIR / "dashboard_post.json"
CRITICAL_NOTIFICATION_PATH = BASE_DIR / "critical_notification.json"


def has_critical_alert(alerts: list[dict]) -> bool:
    return any(alert.get("severity") == "critical" for alert in alerts)


def build_safety_llm_prompt(sensor_data: list[dict], rule_alerts: dict) -> str:
    return f"""
Mode: Safety Auditor Mode

You are receiving:
1. The last 1 hour of raw sensor telemetry.
2. The deterministic rule engine output.

The deterministic rule engine is the source of truth.
Do not invent new alerts.
Do not remove alerts that the rule engine detected.
Do not change severity.
If rule_engine_alerts.alerts is empty, return alerts: [].

Return valid JSON only.

Required output format:

{{
  "mode": "safety_auditor",
  "summary": "Short factual summary.",
  "notification_required": true or false,
  "notification_channel": "dashboard" or "email_sms",
  "alerts": [
    {{
      "alert_name": "string",
      "severity": "low | medium | critical",
      "timestamp": "timestamp",
      "event": "short event description",
      "evidence": ["evidence item"],
      "recommended_action": "short practical recommendation"
    }}
  ],
  "dashboard_post": {{
    "should_post": true,
    "message": "Short dashboard message"
  }},
  "critical_notification": {{
    "should_send": true or false,
    "email_subject": "Short email subject or empty string",
    "email_body": "Short email body or empty string",
    "sms_message": "Short SMS message or empty string"
  }}
}}

Rules:
- Low and medium alerts go to dashboard only.
- Critical alerts require email/SMS notification.
- If no alerts exist, notification_required must be false.

Last 1 hour sensor data:
{json.dumps(sensor_data, indent=2, ensure_ascii=False)}

Rule engine alerts:
{json.dumps(rule_alerts, indent=2, ensure_ascii=False)}
"""


def create_dashboard_post(llm_output: dict) -> dict:
    return {
        "type": "dashboard_post",
        "should_post": bool(llm_output.get("alerts")),
        "notification_required": llm_output.get("notification_required", False),
        "summary": llm_output.get("summary", ""),
        "alerts": llm_output.get("alerts", []),
        "dashboard_post": llm_output.get("dashboard_post", {})
    }


def create_critical_notification(llm_output: dict) -> dict:
    alerts = llm_output.get("alerts", [])
    critical_alerts = [
        alert for alert in alerts
        if alert.get("severity") == "critical"
    ]

    should_send = len(critical_alerts) > 0

    return {
        "type": "critical_notification",
        "should_send": should_send,
        "channels": ["email", "sms"] if should_send else [],
        "critical_alerts": critical_alerts,
        "notification": llm_output.get("critical_notification", {
            "should_send": should_send,
            "email_subject": "",
            "email_body": "",
            "sms_message": ""
        })
    }


def main() -> None:
    sensor_data = fetch_events(lookback_hours=1)
    save_json(sensor_data, HOURLY_SENSOR_DATA_PATH)

    alerts = run_rules(sensor_data)

    rule_alerts = {
        "mode": "rule_engine_safety",
        "window_hours": 1,
        "events_checked": len(sensor_data),
        "summary": (
            f"{len(alerts)} rule-based alert(s) detected."
            if alerts else
            "No rule-based safety alerts detected."
        ),
        "alerts": alerts
    }

    save_json(rule_alerts, RULE_ALERTS_PATH)

    care_plan_prompt = load_care_plan_prompt()
    user_prompt = build_safety_llm_prompt(sensor_data, rule_alerts)

    llm_output = call_ollama_json(care_plan_prompt, user_prompt)
    save_json(llm_output, LLM_SAFETY_OUTPUT_PATH)

    dashboard_post = create_dashboard_post(llm_output)
    save_json(dashboard_post, DASHBOARD_POST_PATH)

    critical_notification = create_critical_notification(llm_output)
    save_json(critical_notification, CRITICAL_NOTIFICATION_PATH)

    print(json.dumps(llm_output, indent=2, ensure_ascii=False))
    print()
    print(f"Hourly sensor data saved to: {HOURLY_SENSOR_DATA_PATH}")
    print(f"Rule alerts saved to: {RULE_ALERTS_PATH}")
    print(f"LLM safety output saved to: {LLM_SAFETY_OUTPUT_PATH}")
    print(f"Dashboard post saved to: {DASHBOARD_POST_PATH}")
    print(f"Critical notification saved to: {CRITICAL_NOTIFICATION_PATH}")


if __name__ == "__main__":
    main()