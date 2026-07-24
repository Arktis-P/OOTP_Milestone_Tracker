"""Fixture-based contract tests for OOTP message milestone automation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinitions, load_milestones
from core.milestone.message_automation import import_message_file, parse_message
from core.milestone.message_automation.tags import team_name_matches
from core.stats.aggregator import Aggregator
from tests.message_automation_contract import (
    ExpectedRecord,
    MessageAutomationAdapter,
    assert_expected_record,
)

ROOT = Path(__file__).resolve().parent.parent
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "message_automation.db")
    yield agg
    agg.close()


@pytest.fixture
def milestones() -> MilestoneDefinitions:
    return load_milestones(MILESTONES_PATH)


@pytest.fixture
def checker(aggregator: Aggregator, milestones: MilestoneDefinitions) -> MilestoneChecker:
    return MilestoneChecker(
        aggregator,
        milestones,
        season_games_total=162,
        tracked_teams=["Seoul Yukies", "Seoul", "SY"],
    )


@pytest.fixture
def message_api() -> MessageAutomationAdapter:
    return MessageAutomationAdapter.discover()


@pytest.mark.parametrize(
    "expected",
    [
        ExpectedRecord(
            fixture="contract_extension_01.txt",
            milestone_key="manual_transfer_extension_contract",
            milestone_label="연장 계약 잔류",
            player_id=45705,
            team=("Seoul Yukies", "Seoul"),
            opponent_team=("", None),
            description="15년 $375,000,000 연장 계약 체결",
            season=2026,
        ),
        ExpectedRecord(
            fixture="award_batter_of_month_02.txt",
            milestone_key="bat_season_award_player_of_month",
            milestone_label="이달의 선수상",
            player_id=53669,
            team="Seoul Yukies",
            opponent_team=("", None),
            description="이달의 타자 (4월) 수상",
            season=2026,
        ),
        ExpectedRecord(
            fixture="award_mvp_02.txt",
            milestone_key="bat_season_award_mvp",
            milestone_label="MVP",
            player_id=53669,
            team="Seoul Yukies",
            opponent_team=("", None),
            description="32표 만장일치로 MVP 수상",
            notes_contains=("Hyeon-min Ahn", "2위", "Shinho Ho", "3위"),
            season=2026,
        ),
        ExpectedRecord(
            fixture="award_cy_young_03.txt",
            milestone_key="pit_season_award_cy_young",
            milestone_label="사이영상",
            player_id=49880,
            team="Seoul Yukies",
            opponent_team=("", None),
            description="20표 187 포인트로 사이영상 수상",
            notes_contains=("Tarik Skubal", "12표", "164포인트", "2위"),
            season=2027,
        ),
        ExpectedRecord(
            fixture="postseason_world_series_01.txt",
            milestone_key="team_season_world_series_win",
            milestone_label="월드시리즈 우승",
            player_id_zero=True,
            team=("Seoul Yukies", "Seoul"),
            opponent_team="Detroit Tigers",
            description="2027 4-0 스윕",
            season=2027,
        ),
        ExpectedRecord(
            fixture="hall_of_fame_01.txt",
            milestone_key="bat_career_hall_of_fame",
            milestone_label="명예의 전당 입성",
            player_id=36987,
            opponent_team=("", None),
            description="KBO League 헌액",
            season=2026,
        ),
    ],
)
def test_message_fixture_core_record_fields(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
    expected: ExpectedRecord,
) -> None:
    records = message_api.parse_records(
        expected.fixture,
        tracked_teams=["Seoul Yukies", "Seoul", "SY"],
        current_season=2026,
        achieved_date=date(2026, 5, 1),
        checker=checker,
        aggregator=checker.aggregator,
        definitions=milestones,
    )

    assert_expected_record(records, expected)


def test_platinum_stick_maps_ootp_name_to_silver_slugger_key(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
) -> None:
    records = message_api.parse_records(
        "award_platinum_stick_02.txt",
        tracked_teams=["Seoul Yukies", "Seoul", "SY"],
        current_season=2026,
        checker=checker,
        aggregator=checker.aggregator,
        definitions=milestones,
    )

    assert len(records) == 8
    assert {record["team"] for record in records} == {"Seoul Yukies"}
    assert {record["milestone_key"] for record in records} == {
        "bat_season_award_silver_slugger"
    }
    assert {record["milestone_label"] for record in records} == {"실버슬러거"}
    assert_expected_record(
        records,
        ExpectedRecord(
            fixture="award_platinum_stick_02.txt",
            milestone_key="bat_season_award_silver_slugger",
            milestone_label="실버슬러거",
            player_id=141875,
            team="Seoul Yukies",
            opponent_team=("", None),
            description="National League C",
            season=2026,
        ),
    )


def test_all_star_roster_filters_to_tracked_team_and_maps_bat_pitch_keys(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
) -> None:
    records = message_api.parse_records(
        "award_all_star_selection_01.txt",
        tracked_teams=["Seoul Yukies", "Seoul", "SY"],
        current_season=2026,
        checker=checker,
        aggregator=checker.aggregator,
        definitions=milestones,
    )

    assert records
    assert {record["team"] for record in records} <= {"Seoul Yukies", "Seoul"}
    assert any(
        record["player_id"] == 53669
        and record["milestone_key"] == "bat_season_award_all_star"
        and record["description"] == "MLB 선발"
        for record in records
    )
    assert all(record.get("opponent_team") in (None, "") for record in records)


def test_trade_fixture_handles_cash_and_tracked_team_perspective(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
) -> None:
    records = message_api.parse_records(
        "trade_multi_player_02.txt",
        tracked_teams=["Milwaukee Brewers", "Milwaukee", "MIL"],
        current_season=2026,
        checker=checker,
        aggregator=checker.aggregator,
        definitions=milestones,
    )

    assert len(records) == 4
    assert_expected_record(
        records,
        ExpectedRecord(
            fixture="trade_multi_player_02.txt",
            milestone_key="manual_transfer_trade",
            milestone_label="트레이드로 합류",
            player_id=21983,
            team=("Milwaukee Brewers", "Milwaukee"),
            opponent_team=("Miami Marlins", "Miami"),
            description="Pete Fairbanks, $5,350,000 <> Bryce Meccage, Andrew Fischer, Chandler Welch 트레이드",
            season=2026,
        ),
    )
    leaving_ids = {
        record["player_id"]
        for record in records
        if record["milestone_label"] == "트레이드로 이탈"
    }
    assert leaving_ids == {55129, 52384, 52914}
    assert all(record["player_id"] != 5350000 for record in records)


def test_injury_fixture_uses_injured_player_not_teammate_tag(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
) -> None:
    records = message_api.parse_records(
        "injury_offfield_02.txt",
        tracked_teams=[],
        current_season=2026,
        checker=checker,
        aggregator=checker.aggregator,
        definitions=milestones,
    )

    assert_expected_record(
        records,
        ExpectedRecord(
            fixture="injury_offfield_02.txt",
            milestone_key="manual_injury",
            milestone_label="부상",
            player_id=42827,
            description_contains=("mild concussion",),
            season=2026,
        ),
    )
    assert all(record["player_id"] != 25951 for record in records)


@pytest.mark.parametrize(
    "fixture",
    [
        "postseason_wildcard_01.txt",
        "postseason_playoff_clinch_01.txt",
        "trade_deadline_news_01.txt",
        "retirement_01.txt",
        "award_all_star_selection_02.txt",
        "hall_of_fame_02.txt",
    ],
)
def test_first_pass_excluded_fixtures_do_not_create_records(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
    fixture: str,
) -> None:
    records = message_api.parse_records(
        fixture,
        tracked_teams=["Seoul Yukies", "Seoul", "SY", "Houston Astros", "Milwaukee Brewers"],
        current_season=2026,
        checker=checker,
        aggregator=checker.aggregator,
        definitions=milestones,
    )

    assert records == []


@pytest.mark.parametrize(
    ("fixture", "reason"),
    [
        ("postseason_wildcard_01.txt", "postseason_wildcard_key_mismatch"),
        ("postseason_playoff_clinch_01.txt", "postseason_playoff_clinch_no_key"),
        ("trade_deadline_news_01.txt", "trade_deadline_not_a_transaction"),
        ("retirement_01.txt", "retirement_milestone_undefined"),
        ("award_all_star_selection_02.txt", "all_star_voting_not_final"),
        ("hall_of_fame_02.txt", "hall_of_fame_voting_not_final"),
    ],
)
def test_first_pass_exclusions_report_stable_reason(
    fixture: str, reason: str
) -> None:
    parsed = parse_message(
        (ROOT / "tests" / "fixtures" / "messages" / fixture).read_text(
            encoding="utf-8"
        ),
        tracked_teams=["Seoul Yukies", "Houston Astros", "Milwaukee Brewers"],
        message_date=date(2026, 5, 1),
        source_id=fixture.removesuffix(".txt"),
    )

    assert parsed.excluded
    assert parsed.exclusion_reason == reason
    assert parsed.forms == []


@pytest.mark.parametrize(
    ("fixture", "expected_key"),
    [
        ("trade_multi_player_01.txt", "manual_transfer_trade"),
        ("trade_multi_player_02.txt", "manual_transfer_trade"),
        ("trade_simple_01.txt", "manual_transfer_trade"),
        ("trade_simple_02.txt", "manual_transfer_trade"),
        ("fa_signing_mlb_01.txt", "manual_transfer_fa_contract"),
        ("fa_signing_mlb_02.txt", "manual_transfer_fa_contract"),
        ("fa_signing_minor_01.txt", "manual_transfer_fa_contract"),
        ("contract_extension_01.txt", "manual_transfer_extension_contract"),
        ("contract_extension_02.txt", "manual_transfer_extension_contract"),
        ("contract_extension_03.txt", "manual_transfer_extension_contract"),
        ("injury_game_01.txt", "manual_injury"),
        ("injury_game_02.txt", "manual_injury"),
        ("injury_game_03.txt", "manual_injury"),
        ("injury_offfield_01.txt", "manual_injury"),
        ("injury_offfield_02.txt", "manual_injury"),
        ("award_mvp_01.txt", "bat_season_award_mvp"),
        ("award_mvp_02.txt", "bat_season_award_mvp"),
        ("award_mvp_03.txt", "bat_season_award_mvp"),
        ("award_cy_young_01.txt", "pit_season_award_cy_young"),
        ("award_cy_young_02.txt", "pit_season_award_cy_young"),
        ("award_cy_young_03.txt", "pit_season_award_cy_young"),
        ("award_great_glove_01.txt", "bat_season_award_gold_glove"),
        ("award_great_glove_02.txt", "bat_season_award_gold_glove"),
        ("award_great_glove_03.txt", "bat_season_award_gold_glove"),
        ("award_platinum_stick_01.txt", "bat_season_award_silver_slugger"),
        ("award_platinum_stick_02.txt", "bat_season_award_silver_slugger"),
        ("award_platinum_stick_03.txt", "bat_season_award_silver_slugger"),
        ("award_rookie_of_year_01.txt", "bat_season_award_rookie_of_year"),
        ("award_rookie_of_year_02.txt", "pit_season_award_rookie_of_year"),
        ("award_batter_of_month_01.txt", "bat_season_award_player_of_month"),
        ("award_batter_of_month_02.txt", "bat_season_award_player_of_month"),
        ("award_pitcher_of_month_01.txt", "pit_season_award_player_of_month"),
        ("award_pitcher_of_month_02.txt", "pit_season_award_player_of_month"),
        ("award_rookie_of_month_01.txt", "bat_season_award_player_of_month"),
        ("award_all_star_selection_01.txt", "bat_season_award_all_star"),
        ("postseason_division_01.txt", "team_season_division_title"),
        ("postseason_division_02.txt", "team_season_division_title"),
        ("postseason_division_03.txt", "team_season_division_title"),
        ("postseason_world_series_01.txt", "team_season_world_series_win"),
        ("hall_of_fame_01.txt", "bat_career_hall_of_fame"),
    ],
)
def test_every_first_pass_fixture_is_recognized(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
    fixture: str,
    expected_key: str,
) -> None:
    records = message_api.parse_records(
        fixture,
        tracked_teams=[],
        current_season=2026,
        checker=checker,
        aggregator=checker.aggregator,
        definitions=milestones,
    )

    assert records, f"{fixture} was not recognized"
    assert expected_key in {record["milestone_key"] for record in records}


def test_same_message_import_is_idempotent(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
    aggregator: Aggregator,
) -> None:
    kwargs = {
        "tracked_teams": ["Seoul Yukies", "Seoul", "SY"],
        "current_season": 2026,
        "achieved_date": date(2026, 5, 1),
        "checker": checker,
        "aggregator": aggregator,
        "definitions": milestones,
    }

    first = message_api.import_fixture("award_mvp_02.txt", **kwargs)
    first_count = aggregator.conn.execute(
        "SELECT COUNT(*) FROM milestone_records"
    ).fetchone()[0]
    second = message_api.import_fixture("award_mvp_02.txt", **kwargs)
    second_count = aggregator.conn.execute(
        "SELECT COUNT(*) FROM milestone_records"
    ).fetchone()[0]

    assert first_count > 0 or first
    assert second_count == first_count
    assert normalize_import_count(second) == 0
    player = aggregator.conn.execute(
        "SELECT full_name, short_name FROM players WHERE player_id = 53669"
    ).fetchone()
    assert player["full_name"] == "Do-young Kim"
    assert player["short_name"]


def test_trade_import_reuses_manual_transfer_field_orientation(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
    aggregator: Aggregator,
) -> None:
    message_api.import_fixture(
        "trade_multi_player_02.txt",
        tracked_teams=["Milwaukee Brewers", "Milwaukee", "MIL"],
        current_season=2026,
        checker=checker,
        aggregator=aggregator,
        definitions=milestones,
    )

    rows = aggregator.conn.execute(
        """
        SELECT player_id, milestone_label, team, opponent_team, description
        FROM milestone_records
        ORDER BY player_id
        """
    ).fetchall()
    assert len(rows) == 4
    joining = next(row for row in rows if row["player_id"] == 21983)
    assert joining["milestone_label"] == "트레이드로 합류"
    assert joining["team"] == "Milwaukee Brewers"
    assert joining["opponent_team"] == "Miami Marlins"
    leaving = next(row for row in rows if row["player_id"] == 52384)
    assert leaving["milestone_label"] == "트레이드로 이탈"
    assert leaving["team"] == "Miami Marlins"
    assert leaving["opponent_team"] == "Milwaukee Brewers"
    assert "$5,350,000" in leaving["description"]


def test_injury_and_team_import_reuse_manual_record_paths(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
    aggregator: Aggregator,
) -> None:
    message_api.import_fixture(
        "injury_game_03.txt",
        tracked_teams=[],
        current_season=2026,
        checker=checker,
        aggregator=aggregator,
        definitions=milestones,
    )
    message_api.import_fixture(
        "postseason_world_series_01.txt",
        tracked_teams=["Seoul Yukies", "Seoul", "SY"],
        current_season=2026,
        checker=checker,
        aggregator=aggregator,
        definitions=milestones,
    )

    injury = aggregator.conn.execute(
        "SELECT * FROM milestone_records WHERE milestone_key = 'manual_injury'"
    ).fetchone()
    assert injury["player_id"] == 39226
    assert injury["milestone_label"] == "부상"
    assert injury["games_at_achievement"] is None
    assert injury["opponent_team"] is None
    team = aggregator.conn.execute(
        """
        SELECT * FROM milestone_records
        WHERE milestone_key = 'team_season_world_series_win'
        """
    ).fetchone()
    assert team["player_id"] == 0
    assert team["team"] == "Seoul Yukies"
    assert team["opponent_team"] == "Detroit Tigers"
    assert team["description"] == "2027 4-0 스윕"


def test_fa_signing_without_previous_team_is_still_an_arrival(
    message_api: MessageAutomationAdapter,
    checker: MilestoneChecker,
    milestones: MilestoneDefinitions,
    aggregator: Aggregator,
) -> None:
    records = message_api.parse_records(
        "fa_signing_mlb_01.txt",
        tracked_teams=["Colorado Rockies", "Colorado", "COL"],
        current_season=2026,
        checker=checker,
        aggregator=aggregator,
        definitions=milestones,
    )
    assert_expected_record(
        records,
        ExpectedRecord(
            fixture="fa_signing_mlb_01.txt",
            milestone_key="manual_transfer_fa_contract",
            milestone_label="FA 계약 합류",
            player_id=33575,
            team="Colorado Rockies",
            opponent_team=("", None),
            description="1년 $4,880,000 FA 계약 체결",
            season=2026,
        ),
    )

    message_api.import_fixture(
        "fa_signing_mlb_01.txt",
        tracked_teams=["Colorado Rockies", "Colorado", "COL"],
        current_season=2026,
        checker=checker,
        aggregator=aggregator,
        definitions=milestones,
    )
    row = aggregator.conn.execute(
        """
        SELECT milestone_label, opponent_team
        FROM milestone_records
        WHERE milestone_key = 'manual_transfer_fa_contract'
        """
    ).fetchone()
    assert row["milestone_label"] == "FA 계약 합류"
    assert row["opponent_team"] is None


def test_tracked_team_prefix_does_not_match_minor_affiliate() -> None:
    assert team_name_matches("Seoul Yukies", "Seoul")
    assert not team_name_matches("Seoul (FCL) Yukies", "Seoul")
    assert not team_name_matches("Seoul", "Seoul (FCL) Yukies")


def test_file_import_service_is_idempotent(
    checker: MilestoneChecker,
    aggregator: Aggregator,
) -> None:
    path = ROOT / "tests" / "fixtures" / "messages" / "contract_extension_01.txt"

    first = import_message_file(
        checker,
        path,
        message_date=date(2026, 5, 1),
        season_hint=2026,
    )
    second = import_message_file(
        checker,
        path,
        message_date=date(2026, 5, 1),
        season_hint=2026,
    )

    assert first.recorded_count == 1
    assert second.recorded_count == 0
    assert aggregator.conn.execute(
        "SELECT COUNT(*) FROM milestone_records"
    ).fetchone()[0] == 1


def normalize_import_count(result: list[dict[str, object]]) -> int:
    if len(result) == 1:
        row = result[0]
        for key in ("created_count", "recorded_count", "inserted_count", "count"):
            if key in row:
                return int(row[key] or 0)
        for key in ("created_ids", "record_ids", "inserted_ids", "ids"):
            if key in row and isinstance(row[key], list):
                return len(row[key])
    return len(result)
