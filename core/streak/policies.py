"""Streak milestone policy loading and label helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config.paths import resolve_data_path
from core.stats.ip_utils import outs_to_ip_str


def default_policies_path() -> Path:
    return resolve_data_path("data/streak_policies.json")


def load_streak_policies(path: str | Path | None = None) -> dict[str, Any]:
    policy_path = Path(path) if path else default_policies_path()
    with policy_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def policy_min_value(policy: dict[str, Any]) -> int:
    """Minimum streak length (or outs for IP streak) required to record on break."""
    if "min_value" in policy:
        return int(policy["min_value"])
    return int(policy.get("ended_event_min_value", 999999))


def should_record_streak_on_break(ended_value: int, policy: dict[str, Any]) -> bool:
    return ended_value >= policy_min_value(policy)


def format_streak_value(value: int, policy: dict[str, Any]) -> str:
    if policy.get("unit") == "outs":
        return outs_to_ip_str(value)
    return str(value)


def streak_record_label(streak_type: str, value: int, policies: dict[str, Any]) -> str:
    """Label for a completed streak recorded when the run ends."""
    labels = policies.get("labels") or {}
    name = labels.get(streak_type, streak_type)
    policy = _policy_for_type(streak_type, policies)
    if policy and policy.get("unit") == "outs":
        return f"{format_streak_value(value, policy)} {name}"
    return f"{value}경기 {name}"


def _policy_for_type(streak_type: str, policies: dict[str, Any]) -> dict[str, Any] | None:
    for group in ("batting", "pitching"):
        bucket = policies.get(group) or {}
        if streak_type in bucket:
            return bucket[streak_type]
    return None


def batting_policies(policies: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return dict(policies.get("batting") or {})


def pitching_policies(policies: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return dict(policies.get("pitching") or {})


# Backward-compatible aliases for export / older callers
def should_record_ended_event(ended_value: int, policy: dict[str, Any]) -> bool:
    return should_record_streak_on_break(ended_value, policy)


def ongoing_label(streak_type: str, value: int, policies: dict[str, Any]) -> str:
    return streak_record_label(streak_type, value, policies)


def ended_label(streak_type: str, value: int, policies: dict[str, Any]) -> str:
    return streak_record_label(streak_type, value, policies)
