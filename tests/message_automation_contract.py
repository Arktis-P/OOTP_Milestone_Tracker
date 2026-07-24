"""Shared contract helpers for OOTP message automation fixture tests."""

from __future__ import annotations

import importlib
import inspect
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pytest

from core.milestone.manual_entry import (
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "messages"


@dataclass(frozen=True)
class ExpectedRecord:
    fixture: str
    milestone_key: str
    milestone_label: str
    player_id: int | None = None
    team: str | tuple[str, ...] | None = None
    opponent_team: str | tuple[str, ...] | None = None
    description: str | None = None
    description_contains: str | tuple[str, ...] | None = None
    notes_contains: str | tuple[str, ...] | None = None
    season: int | None = None
    achieved_value: float | None = 1.0
    games_at_achievement: None = None
    player_id_zero: bool = False


class MessageAutomationAdapter:
    """Small compatibility layer for the in-flight parser/importer API.

    The production API is being implemented in parallel. These tests pin the
    behavioral contract to the agreed public functions.
    """

    MODULE_CANDIDATES = (
        "core.milestone.message_automation",
    )
    PARSE_FUNCTIONS = (
        "parse_message",
    )
    IMPORT_FUNCTIONS = (
        "apply_parsed_messages",
    )

    def __init__(self, module: Any) -> None:
        self.module = module
        self.parse_func = self._find_callable(self.PARSE_FUNCTIONS)
        self.import_func = self._find_callable(self.IMPORT_FUNCTIONS)

    @classmethod
    def discover(cls) -> "MessageAutomationAdapter":
        for module_name in cls.MODULE_CANDIDATES:
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                continue
            adapter = cls(module)
            if adapter.parse_func:
                return adapter
        pytest.fail(
            "core.milestone.message_automation.parse_message is required "
            "for message automation fixture tests"
        )

    def parse_records(
        self,
        fixture: str,
        *,
        tracked_teams: list[str] | None = None,
        current_season: int = 2026,
        achieved_date: date = date(2026, 5, 1),
        aggregator: Any | None = None,
        checker: Any | None = None,
        definitions: Any | None = None,
    ) -> list[dict[str, Any]]:
        if self.parse_func is None:
            pytest.fail("parse_message is required for message automation fixture tests")
        result = self._call_message_api(
            self.parse_func,
            fixture,
            tracked_teams=tracked_teams,
            current_season=current_season,
            achieved_date=achieved_date,
            aggregator=aggregator,
            checker=checker,
            definitions=definitions,
        )
        return normalize_records(result)

    def import_fixture(
        self,
        fixture: str,
        *,
        tracked_teams: list[str] | None = None,
        current_season: int = 2026,
        achieved_date: date = date(2026, 5, 1),
        aggregator: Any | None = None,
        checker: Any | None = None,
        definitions: Any | None = None,
    ) -> list[dict[str, Any]]:
        if self.import_func is None:
            pytest.fail(
                "apply_parsed_messages is required for message automation idempotency tests"
            )
        if self.import_func.__name__ == "apply_parsed_messages":
            if self.parse_func is None:
                pytest.fail("parse_message is required before apply_parsed_messages")
            parsed = self._call_message_api(
                self.parse_func,
                fixture,
                tracked_teams=tracked_teams,
                current_season=current_season,
                achieved_date=achieved_date,
                aggregator=aggregator,
                checker=checker,
                definitions=definitions,
            )
            result = self._call_apply_api(
                self.import_func,
                parsed,
                tracked_teams=tracked_teams,
                current_season=current_season,
                achieved_date=achieved_date,
                aggregator=aggregator,
                checker=checker,
                definitions=definitions,
            )
            return normalize_records(result)
        result = self._call_message_api(
            self.import_func,
            fixture,
            tracked_teams=tracked_teams,
            current_season=current_season,
            achieved_date=achieved_date,
            aggregator=aggregator,
            checker=checker,
            definitions=definitions,
        )
        return normalize_records(result)

    def _find_callable(self, names: tuple[str, ...]) -> Callable[..., Any] | None:
        for name in names:
            candidate = getattr(self.module, name, None)
            if callable(candidate):
                return candidate
        return None

    def _call_message_api(
        self,
        func: Callable[..., Any],
        fixture: str,
        *,
        tracked_teams: list[str] | None,
        current_season: int,
        achieved_date: date,
        aggregator: Any | None,
        checker: Any | None,
        definitions: Any | None,
    ) -> Any:
        path = FIXTURES_DIR / fixture
        text = path.read_text(encoding="utf-8")
        kwargs: dict[str, Any] = {}
        signature = inspect.signature(func)
        params = signature.parameters

        if "path" in params:
            kwargs["path"] = path
        if "message_path" in params:
            kwargs["message_path"] = path
        if "fixture_path" in params:
            kwargs["fixture_path"] = path
        if "message_file" in params:
            kwargs["message_file"] = path
        if "text" in params:
            kwargs["text"] = text
        if "message_text" in params:
            kwargs["message_text"] = text
        if "message" in params:
            kwargs["message"] = text
        if "filename" in params:
            kwargs["filename"] = fixture
        if "source_id" in params:
            kwargs["source_id"] = fixture.removesuffix(".txt")
        if "tracked_teams" in params:
            kwargs["tracked_teams"] = (
                ["Seoul Yukies", "Seoul", "SY"]
                if tracked_teams is None
                else tracked_teams
            )
        if "current_season" in params:
            kwargs["current_season"] = current_season
        if "season" in params:
            kwargs["season"] = current_season
        if "achieved_date" in params:
            kwargs["achieved_date"] = achieved_date
        if "message_date" in params:
            kwargs["message_date"] = achieved_date
        if "aggregator" in params and aggregator is not None:
            kwargs["aggregator"] = aggregator
        if "checker" in params and checker is not None:
            kwargs["checker"] = checker
        if "definitions" in params and definitions is not None:
            kwargs["definitions"] = definitions

        if not kwargs:
            return func(path)
        missing_required = [
            name
            for name, param in params.items()
            if param.default is inspect.Parameter.empty
            and param.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and name not in kwargs
        ]
        if missing_required:
            first = missing_required[0]
            if "text" in first or "message" in first:
                kwargs[first] = text
            else:
                kwargs[first] = path
        return func(**kwargs)

    def _call_apply_api(
        self,
        func: Callable[..., Any],
        parsed: Any,
        *,
        tracked_teams: list[str] | None,
        current_season: int,
        achieved_date: date,
        aggregator: Any | None,
        checker: Any | None,
        definitions: Any | None,
    ) -> Any:
        kwargs: dict[str, Any] = {}
        signature = inspect.signature(func)
        params = signature.parameters
        for name in ("records", "parsed_records", "messages", "parsed_messages", "items"):
            if name in params:
                kwargs[name] = parsed
                break
        if "tracked_teams" in params:
            kwargs["tracked_teams"] = (
                ["Seoul Yukies", "Seoul", "SY"]
                if tracked_teams is None
                else tracked_teams
            )
        if "current_season" in params:
            kwargs["current_season"] = current_season
        if "season" in params:
            kwargs["season"] = current_season
        if "achieved_date" in params:
            kwargs["achieved_date"] = achieved_date
        if "message_date" in params:
            kwargs["message_date"] = achieved_date
        if "aggregator" in params and aggregator is not None:
            kwargs["aggregator"] = aggregator
        if "checker" in params and checker is not None:
            kwargs["checker"] = checker
        if "definitions" in params and definitions is not None:
            kwargs["definitions"] = definitions
        if "conn" in params and aggregator is not None:
            kwargs["conn"] = aggregator.conn

        missing_required = [
            name
            for name, param in params.items()
            if param.default is inspect.Parameter.empty
            and param.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and name not in kwargs
        ]
        if missing_required:
            kwargs[missing_required[0]] = parsed
        return func(**kwargs)


def normalize_records(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    if hasattr(result, "forms"):
        return _normalize_forms(list(result.forms))
    if isinstance(result, dict):
        for key in ("records", "created_records", "achievements", "items"):
            if key in result:
                return normalize_records(result[key])
        return [_normalize_one(result)]
    if isinstance(result, (str, bytes)):
        raise TypeError("message automation API returned text instead of records")
    if isinstance(result, int):
        return []
    return [_normalize_one(item) for item in list(result)]


def _normalize_forms(forms: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for form in forms:
        if isinstance(form, ManualMilestoneFormData):
            records.append(
                {
                    "milestone_key": form.milestone_key,
                    "milestone_label": _label_for_key(form.milestone_key),
                    "player_id": 0 if form.target == "team" else form.player_id,
                    "team": form.team,
                    "opponent_team": form.opponent_team,
                    "description": form.description,
                    "notes": form.notes,
                    "season": form.season,
                    "achieved_value": form.achieved_value,
                    "games_at_achievement": form.games_at_achievement,
                }
            )
        elif isinstance(form, ManualTransferFormData):
            for token in _player_refs(form.joining_players):
                records.append(
                    _transfer_record(form, token, joining=True)
                )
            for token in _player_refs(form.leaving_players):
                records.append(
                    _transfer_record(form, token, joining=False)
                )
        elif isinstance(form, ManualInjuryFormData):
            records.append(
                {
                    "milestone_key": "manual_injury",
                    "milestone_label": "부상",
                    "player_id": _player_id_from_ref(form.player_name),
                    "team": form.team,
                    "opponent_team": "",
                    "description": form.description,
                    "notes": form.notes,
                    "season": form.season,
                    "achieved_value": 1.0,
                    "games_at_achievement": None,
                }
            )
    return records


def _transfer_record(
    form: ManualTransferFormData, token: str, *, joining: bool
) -> dict[str, Any]:
    if form.event_type == "trade":
        label = "트레이드로 합류" if joining else "트레이드로 이탈"
    elif form.event_type == "extension_contract":
        label = "연장 계약 잔류"
    else:
        is_retention = (
            form.fa_is_retention
            if form.fa_is_retention is not None
            else not form.counterpart_team
        )
        label = "FA 계약 잔류" if is_retention else "FA 계약 합류"
    return {
        "milestone_key": f"manual_transfer_{form.event_type}",
        "milestone_label": label,
        "player_id": _player_id_from_ref(token),
        "team": form.join_team if joining else form.counterpart_team,
        "opponent_team": form.counterpart_team if joining else form.join_team,
        "description": form.description,
        "notes": form.notes,
        "season": form.season,
        "achieved_value": 1.0,
        "games_at_achievement": None,
    }


def _player_id_from_ref(text: str) -> int | None:
    match = re.search(r"\(#(\d+)\)", text)
    return int(match.group(1)) if match else None


def _player_refs(text: str) -> list[str]:
    return [
        match.group(0)
        for match in re.finditer(r"[^,]+?\s*\(#\d+\)", text)
    ]


def _label_for_key(key: str) -> str:
    if key.endswith("_award_mvp"):
        return "MVP"
    if key.endswith("_award_cy_young"):
        return "사이영상"
    if key.endswith("_award_gold_glove"):
        return "골드글러브"
    if key.endswith("_award_silver_slugger"):
        return "실버슬러거"
    if key.endswith("_award_rookie_of_year"):
        return "신인왕"
    if key.endswith("_award_player_of_month"):
        return "이달의 선수상"
    if key.endswith("_award_all_star"):
        return "올스타"
    if key == "team_season_division_title":
        return "지구 우승"
    if key == "team_season_world_series_win":
        return "월드시리즈 우승"
    if key.endswith("_career_hall_of_fame"):
        return "명예의 전당 입성"
    return key


def _normalize_one(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        data = dict(item)
    else:
        data = {
            name: getattr(item, name)
            for name in dir(item)
            if not name.startswith("_") and not callable(getattr(item, name))
        }
    milestone = data.get("milestone")
    if milestone is not None:
        data.setdefault("milestone_key", getattr(milestone, "key", None))
        data.setdefault("milestone_label", getattr(milestone, "label", None))
    if "label" in data and "milestone_label" not in data:
        data["milestone_label"] = data["label"]
    return data


def assert_expected_record(records: list[dict[str, Any]], expected: ExpectedRecord) -> dict[str, Any]:
    matches = [
        record
        for record in records
        if record.get("milestone_key") == expected.milestone_key
        and record.get("milestone_label") == expected.milestone_label
        and _matches(record.get("player_id"), 0 if expected.player_id_zero else expected.player_id)
        and _matches(record.get("team"), expected.team)
        and _matches(record.get("opponent_team"), expected.opponent_team)
    ]
    assert matches, f"{expected.fixture}: expected record not found in {records!r}"
    record = matches[0]

    if expected.description is not None:
        assert record.get("description") == expected.description
    for needle in _as_tuple(expected.description_contains):
        assert needle in str(record.get("description") or "")
    for needle in _as_tuple(expected.notes_contains):
        assert needle in str(record.get("notes") or "")
    if expected.season is not None:
        assert record.get("season") == expected.season
    if expected.achieved_value is not None:
        assert float(record.get("achieved_value", 1.0)) == expected.achieved_value
    assert record.get("games_at_achievement") is None
    return record


def _matches(actual: Any, expected: Any) -> bool:
    if expected is None:
        return True
    if isinstance(expected, tuple):
        return actual in expected
    return actual == expected


def _as_tuple(value: str | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return (value,)
