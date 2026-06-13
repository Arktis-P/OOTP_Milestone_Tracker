"""Manual milestone entry helpers and persistence."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinition, load_milestones
from core.milestone.manual_entry import (
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
    build_injury_description,
    build_trade_description,
    build_transfer_records,
    check_duplicate,
    get_achieved_value_candidates,
    milestones_for_manual_entry,
    parse_flexible_date,
    parse_player_name_list,
    validate_manual_entry,
    validate_manual_injury,
    validate_manual_transfer,
)
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
MILESTONES_PATH = ROOT / "data" / "milestones.csv"
GIANTS = "San Francisco Giants"
RED_SOX = "Boston Red Sox"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "manual.db")
    yield agg
    agg.close()


@pytest.fixture
def milestones():
    return load_milestones(MILESTONES_PATH)


@pytest.fixture
def checker(aggregator: Aggregator, milestones) -> MilestoneChecker:
    return MilestoneChecker(aggregator, milestones, season_games_total=162)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("260301", date(2026, 3, 1)),
        ("26/03/01", date(2026, 3, 1)),
        ("26-03-01", date(2026, 3, 1)),
        ("2026-03-01", date(2026, 3, 1)),
        ("2026/03/01", date(2026, 3, 1)),
        ("20260301", date(2026, 3, 1)),
    ],
)
def test_parse_flexible_date_formats(text: str, expected: date) -> None:
    assert parse_flexible_date(text) == expected


def test_parse_flexible_date_invalid() -> None:
    assert parse_flexible_date("not-a-date") is None
    assert parse_flexible_date("2026-13-01") is None


def test_achieved_value_candidates_higher(milestones) -> None:
    milestone = milestones.get_by_key("bat_career_hr_500")
    assert milestone is not None
    assert get_achieved_value_candidates(milestone) == ["500", "501", "502", "503"]


def test_achieved_value_candidates_lower() -> None:
    milestone = MilestoneDefinition(
        key="test_era",
        label="ERA 2.00 이하",
        stat="era",
        threshold=2.0,
        scope="season",
        category="pitching",
        direction="lower",
    )
    assert get_achieved_value_candidates(milestone) == ["2", "1", "0", "-1"]


def _seed_player(
    aggregator: Aggregator,
    player_id: int = 42,
    *,
    full_name: str = "Aaron Judge",
    short_name: str = "A. Judge",
) -> None:
    aggregator.conn.execute(
        """
        INSERT INTO players (player_id, full_name, short_name)
        VALUES (?, ?, ?)
        """,
        (player_id, full_name, short_name),
    )
    aggregator.conn.commit()


def test_record_manual_player_milestone(checker: MilestoneChecker, aggregator) -> None:
    _seed_player(aggregator)
    milestone = checker.definitions.get_by_key("bat_career_hr_500")
    assert milestone is not None
    form = ManualMilestoneFormData(
        target="player",
        achieved_date=date(2026, 3, 1),
        player_id=42,
        team=None,
        milestone_key="bat_career_hr_500",
        season=None,
        achieved_value=500.0,
        games_at_achievement=1800,
        opponent_team="Boston Red Sox",
        opponent_player="",
        description="통산 500호",
        notes="수동 메모",
    )
    assert validate_manual_entry(form, milestone) == []
    record_id = checker.record_manual_milestone(form)
    row = aggregator.conn.execute(
        "SELECT * FROM milestone_records WHERE id = ?",
        (record_id,),
    ).fetchone()
    assert row["player_id"] == 42
    assert row["team"] is None
    assert row["is_manual"] == 1
    assert row["game_id"] is None
    assert row["opponent_team"] == "Boston Red Sox"
    assert row["description"] == "통산 500호"
    assert row["games_at_achievement"] == 1800


def test_record_manual_team_milestone(checker: MilestoneChecker, aggregator) -> None:
    milestone = checker.definitions.get_by_key("team_season_world_series_win")
    assert milestone is not None
    form = ManualMilestoneFormData(
        target="team",
        achieved_date=date(2026, 10, 30),
        player_id=None,
        team=GIANTS,
        milestone_key="team_season_world_series_win",
        season=2026,
        achieved_value=1.0,
        games_at_achievement=162,
        opponent_team="",
        opponent_player="",
        description="",
        notes="우승",
    )
    assert validate_manual_entry(form, milestone) == []
    record_id = checker.record_manual_milestone(form)
    row = aggregator.conn.execute(
        "SELECT * FROM milestone_records WHERE id = ?",
        (record_id,),
    ).fetchone()
    assert row["player_id"] == 0
    assert row["team"] == GIANTS
    assert row["is_manual"] == 1
    assert row["season"] == 2026


def test_check_duplicate_career_warns(checker: MilestoneChecker, aggregator) -> None:
    _seed_player(aggregator)
    milestone = checker.definitions.get_by_key("bat_career_hr_500")
    assert milestone is not None
    form = ManualMilestoneFormData(
        target="player",
        achieved_date=date(2026, 3, 1),
        player_id=42,
        team=None,
        milestone_key="bat_career_hr_500",
        season=None,
        achieved_value=500.0,
        games_at_achievement=100,
        opponent_team="",
        opponent_player="",
        description="",
        notes="",
    )
    checker.record_manual_milestone(form)
    kind, msg = check_duplicate(aggregator.conn, form, milestone)
    assert kind == "warn"
    assert "통산" in msg


def test_check_duplicate_same_date_game_scope_warns(
    checker: MilestoneChecker, aggregator
) -> None:
    _seed_player(aggregator)
    milestone = checker.definitions.get_by_key("bat_game_hr_2")
    assert milestone is not None
    form = ManualMilestoneFormData(
        target="player",
        achieved_date=date(2026, 4, 5),
        player_id=42,
        team=None,
        milestone_key="bat_game_hr_2",
        season=None,
        achieved_value=2.0,
        games_at_achievement=None,
        opponent_team="",
        opponent_player="",
        description="",
        notes="",
    )
    checker.record_manual_milestone(form)
    kind, msg = check_duplicate(aggregator.conn, form, milestone)
    assert kind == "warn"
    assert "같은 날짜" in msg


def test_milestones_for_manual_entry_splits_awards(milestones) -> None:
    general = milestones_for_manual_entry(
        milestones.all_milestones, "player", category="milestone"
    )
    awards = milestones_for_manual_entry(
        milestones.all_milestones, "player", category="award"
    )
    assert milestones.get_by_key("bat_career_hr_500") in general
    assert milestones.get_by_key("bat_season_award_mvp") in awards
    assert milestones.get_by_key("bat_career_hr_500") not in awards
    assert milestones.get_by_key("bat_season_award_mvp") not in general


def test_parse_player_name_list() -> None:
    assert parse_player_name_list("A. Judge, M. Trout") == ["A. Judge", "M. Trout"]
    assert parse_player_name_list("[B] A. Judge (#42), B. Harper") == [
        "A. Judge",
        "B. Harper",
    ]


def test_build_trade_description() -> None:
    assert build_trade_description(["A. Judge"], ["B. Harper"]) == (
        "A. Judge <> B. Harper 트레이드"
    )


def test_build_injury_description() -> None:
    assert build_injury_description("햄스트링", "3일") == "햄스트링으로 3일 진단"
    assert build_injury_description("어깨", "") == "어깨로 결장"


def test_build_transfer_records_trade(aggregator) -> None:
    _seed_player(aggregator, 42, short_name="A. Judge")
    _seed_player(aggregator, 43, full_name="Bryce Harper", short_name="B. Harper")
    form = ManualTransferFormData(
        achieved_date=date(2026, 7, 1),
        joining_players="A. Judge",
        leaving_players="B. Harper",
        event_type="trade",
        join_team=GIANTS,
        counterpart_team=RED_SOX,
        season=2026,
        description="A. Judge <> B. Harper 트레이드 + 현금",
        notes="",
    )
    records, errors = build_transfer_records(aggregator.conn, form)
    assert errors == []
    assert len(records) == 2
    assert records[0].label == "트레이드로 합류"
    assert records[0].team == GIANTS
    assert records[0].opponent_team == RED_SOX
    assert records[1].label == "트레이드로 이탈"
    assert records[1].team == RED_SOX
    assert records[1].opponent_team == GIANTS


def test_build_transfer_records_fa_contract(aggregator) -> None:
    _seed_player(aggregator, 42, short_name="A. Judge")
    _seed_player(aggregator, 43, short_name="B. Harper")
    form = ManualTransferFormData(
        achieved_date=date(2026, 7, 1),
        joining_players="A. Judge",
        leaving_players="B. Harper",
        event_type="fa_contract",
        join_team=GIANTS,
        counterpart_team=RED_SOX,
        season=2026,
        description="",
        notes="",
    )
    records, errors = build_transfer_records(aggregator.conn, form)
    assert errors == []
    assert records[0].label == "FA 계약 합류"
    assert records[1].label == "FA 계약 이탈"


def test_build_transfer_records_fa_retention(aggregator) -> None:
    _seed_player(aggregator, 42, short_name="A. Judge")
    form = ManualTransferFormData(
        achieved_date=date(2026, 7, 1),
        joining_players="A. Judge",
        leaving_players="",
        event_type="fa_contract",
        join_team=GIANTS,
        counterpart_team="",
        season=2026,
        description="",
        notes="",
    )
    records, errors = build_transfer_records(aggregator.conn, form)
    assert errors == []
    assert records[0].label == "FA 계약 잔류"
    assert records[0].opponent_team is None


def test_record_manual_transfer_creates_multiple_rows(
    checker: MilestoneChecker, aggregator
) -> None:
    _seed_player(aggregator, 42, short_name="A. Judge")
    _seed_player(aggregator, 43, short_name="B. Harper")
    form = ManualTransferFormData(
        achieved_date=date(2026, 7, 1),
        joining_players="A. Judge",
        leaving_players="B. Harper",
        event_type="trade",
        join_team=GIANTS,
        counterpart_team=RED_SOX,
        season=2026,
        description="트레이드",
        notes="",
    )
    ids = checker.record_manual_transfer(form)
    assert len(ids) == 2
    rows = aggregator.conn.execute(
        "SELECT milestone_label, team, opponent_team FROM milestone_records ORDER BY id"
    ).fetchall()
    assert rows[0]["milestone_label"] == "트레이드로 합류"
    assert rows[0]["team"] == GIANTS
    assert rows[1]["milestone_label"] == "트레이드로 이탈"
    assert rows[1]["team"] == RED_SOX


def test_record_manual_injury(checker: MilestoneChecker, aggregator) -> None:
    _seed_player(aggregator)
    form = ManualInjuryFormData(
        player_name="A. Judge",
        achieved_date=date(2026, 5, 10),
        injury_label="햄스트링",
        duration="3일",
        team=GIANTS,
        season=2026,
        description="",
        notes="",
    )
    assert validate_manual_injury(form) == []
    record_id = checker.record_manual_injury(form)
    row = aggregator.conn.execute(
        "SELECT * FROM milestone_records WHERE id = ?",
        (record_id,),
    ).fetchone()
    assert row["milestone_key"] == "manual_injury"
    assert row["milestone_label"] == "부상"
    assert row["scope"] == "manual_event"
    assert row["team"] == GIANTS
    assert row["description"] == "햄스트링으로 3일 진단"
