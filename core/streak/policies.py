"""Streak milestone policy loading and label helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.stats.ip_utils import outs_to_ip_str

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_POLICIES_PATH = ROOT / "data" / "streak_policies.json"


def load_streak_policies(path: str | Path | None = None) -> dict[str, Any]:
    policy_path = Path(path) if path else DEFAULT_POLICIES_PATH
    with policy_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def is_milestone_value(value: int, policy: dict[str, Any]) -> bool:
    fixed = set(policy.get("fixed_milestones") or [])
    repeat_after = policy.get("repeat_after")
    repeat_step = int(policy.get("repeat_step") or 1)

    if value in fixed:
        return True

    if repeat_after is not None and value > int(repeat_after):
        return (value - int(repeat_after)) % repeat_step == 0

    return False


def should_record_ended_event(ended_value: int, policy: dict[str, Any]) -> bool:
    return ended_value >= int(policy.get("ended_event_min_value", 999999))


def format_streak_value(value: int, policy: dict[str, Any]) -> str:
    if policy.get("unit") == "outs":
        return outs_to_ip_str(value)
    return str(value)


def ongoing_label(streak_type: str, value: int, policies: dict[str, Any]) -> str:
    labels = policies.get("labels") or {}
    name = labels.get(streak_type, streak_type)
    policy = _policy_for_type(streak_type, policies)
    if policy and policy.get("unit") == "outs":
        return f"{format_streak_value(value, policy)}이닝 {name}"
    return f"{value}경기 {name}"


def ended_label(streak_type: str, value: int, policies: dict[str, Any]) -> str:
    labels = policies.get("labels") or {}
    name = labels.get(streak_type, streak_type)
    policy = _policy_for_type(streak_type, policies)
    if policy and policy.get("unit") == "outs":
        return f"{format_streak_value(value, policy)} {name} 기록 종료"
    return f"{value}경기 {name} 기록 종료"


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
