import argparse
import json
from pathlib import Path
from llm_client import load_prompt

from fetch_events import fetch_events, fetch_events_between, parse_datetime
from rule_alerts import (
    check_fridge_left_open,
    check_water_running_no_bathroom,
    check_long_sedentary_period,
    check_stove_on_left_or_sleep,
    check_night_exit,
    check_door_open_at_night,
    check_door_open_while_sleeping,
)
from llm_client import load_prompt, call_ollama_json, save_json

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
SAFETY_PROMPT_PATH = PROJECT_DIR / "LLM_Safety_Prompt.md"

HOURLY_SENSOR_DATA_PATH = BASE_DIR / "sensor_data_hourly.json"
SAFETY_RULE_ALERTS_PATH = BASE_DIR / "safety_rule_alerts.json"
LLM_SAFETY_OUTPUT_PATH = BASE_DIR / "llm_safety_output.json"
DASHBOARD_POST_PATH = BASE_DIR / "dashboard_post.json"
DASHBOARD_24H_PATH = BASE_DIR / "dashboard_posts_24h.json"
CRITICAL_NOTIFICATION_PATH = BASE_DIR / "critical_notification.json"


def run_safety_rules(events):
    alerts = []
    alerts.extend(check_fridge_left_open(events))
    alerts.extend(check_water_running_no_bathroom(events))
    alerts.extend(check_long_sedentary_period(events))
    alerts.extend(check_stove_on_left_or_sleep(events))
    alerts.extend(check_night_exit(events))
    alerts.extend(check_door_open_at_night(events))
    alerts.extend(check_door_open_while_sleeping(events))
    return alerts


def highest_severity(alerts):
    order = {"low": 1, "medium": 2, "critical": 3}
    if not alerts:
        return "none"
    return max(alerts, key=lambda alert: order.get(alert.get("severity"), 0)).get("severity", "none")


def has_critical_alert(alerts):
    return any(alert.get("severity") == "critical" for alert in alerts)


def build_direct_dashboard_output(alerts):
    if not alerts:
        return {
            "mode": "safety_auditor",
            "should_post_to_dashboard": False,
            "highest_severity": "none",
            "summary": "No safety alerts were detected in this hour.",
            "alerts": []
        }

    return {
        "mode": "safety_auditor",
        "should_post_to_dashboard": True,
        "highest_severity": highest_severity(alerts),
        "summary": f"{len(alerts)} rule-based safety alert(s) detected.",
        "alerts": alerts
    }


def build_critical_notification(alerts):
    critical_alerts = [
        alert for alert in alerts
        if alert.get("severity") == "critical"
    ]

    return {
        "type": "critical_notification",
        "should_send": bool(critical_alerts),
        "critical_alerts": critical_alerts
    }


def build_llm_prompt(sensor_data, rule_alerts):
    return f"""
Mode: Safety Auditor Mode

You receive:
1. Last-hour sensor data.
2. Rule-engine safety alerts.

The Python rule engine is the source of truth.
Do not create new alerts.
Do not remove alerts.
Do not change alert_name, severity, timestamp, or evidence.
Only make the output dashboard-friendly and human readable.

Only critical alerts are sent to the LLM. Low and medium alerts are handled directly by Python.

Return only valid JSON in this structure:

{{
  "mode": "safety_auditor",
  "should_post_to_dashboard": true,
  "highest_severity": "critical",
  "summary": "Short human-readable summary.",
  "alerts": [
    {{
      "alert_name": "string",
      "severity": "critical",
      "timestamp": "timestamp",
      "dashboard_title": "short title",
      "dashboard_message": "human-readable message",
      "evidence": ["evidence item"],
      "recommended_action": "short practical recommendation"
    }}
  ]
}}

Sensor data:
{json.dumps(sensor_data, indent=2, ensure_ascii=False)}

Rule-engine safety alerts:
{json.dumps(rule_alerts, indent=2, ensure_ascii=False)}
"""


def append_compact_dashboard_posts(llm_output):
    alerts = llm_output.get("alerts", [])

    if DASHBOARD_24H_PATH.exists():
        with DASHBOARD_24H_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    else:
        data = {"posts": []}

    for alert in alerts:
        data["posts"].append({
            "timestamp": alert.get("timestamp"),
            "alert_name": alert.get("alert_name"),
            "severity": alert.get("severity")
        })

    with DASHBOARD_24H_PATH.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=1)
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    args = parser.parse_args()

    if args.start and args.end:
        sensor_data = fetch_events_between(
            parse_datetime(args.start),
            parse_datetime(args.end)
        )
    else:
        sensor_data = fetch_events(args.hours)

    save_json(sensor_data, HOURLY_SENSOR_DATA_PATH)

    alerts = run_safety_rules(sensor_data)

    rule_alerts = {
        "mode": "safety_rule_engine",
        "events_checked": len(sensor_data),
        "highest_severity": highest_severity(alerts),
        "alerts": alerts
    }

    save_json(rule_alerts, SAFETY_RULE_ALERTS_PATH)

    if not alerts:
        llm_output = build_direct_dashboard_output(alerts)

    elif not has_critical_alert(alerts):
        llm_output = build_direct_dashboard_output(alerts)

    else:
        system_prompt = load_prompt(SAFETY_PROMPT_PATH)
        user_prompt = build_llm_prompt(sensor_data, rule_alerts)
        llm_output = call_ollama_json(system_prompt, user_prompt)

        if llm_output.get("mode") == "llm_error":
            llm_output = build_direct_dashboard_output(alerts)

    save_json(llm_output, LLM_SAFETY_OUTPUT_PATH)

    dashboard_post = {
        "type": "dashboard_post",
        "should_post": bool(llm_output.get("alerts")),
        "highest_severity": llm_output.get("highest_severity", "none"),
        "summary": llm_output.get("summary", ""),
        "alerts": llm_output.get("alerts", [])
    }

    save_json(dashboard_post, DASHBOARD_POST_PATH)

    critical_notification = build_critical_notification(dashboard_post["alerts"])
    save_json(critical_notification, CRITICAL_NOTIFICATION_PATH)

    append_compact_dashboard_posts(llm_output)

    print(json.dumps(dashboard_post, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()