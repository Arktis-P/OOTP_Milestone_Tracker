"""Milestone checker tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.db.meta import set_meta
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions, load_milestones
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter
from core.stats.models import BoxscoreData, GameMeta, PitcherLine
from core.stats.pitching_special import detect_special_game

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"
SAMPLES_STATS = ROOT / "samples" / "player_stats_txt"
MILESTONES_PATH = ROOT / "data" / "milestones.csv"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    agg = Aggregator(tmp_path / "test.db")
    yield agg
    agg.close()


@pytest.fixture
def milestones() -> MilestoneDefinitions:
    return load_milestones(MILESTONES_PATH)


@pytest.fixture
def checker(aggregator: Aggregator, milestones: MilestoneDefinitions) -> MilestoneChecker:
    return MilestoneChecker(aggregator, milestones, season_games_total=162)


def _import_games(aggregator: Aggregator, *names: str, season: int = 2026) -> list[int]:
    imported: list[int] = []
    for name in names:
        data = BoxscoreHTMLParser(SAMPLES_BOX / name).parse()
        result = aggregator.import_boxscore(data, season=season)
        assert result.error is None
        imported.append(data.meta.game_id)
    return imported


def test_load_milestones_csv_grade(milestones: MilestoneDefinitions) -> None:
    perfect = milestones.get_by_key("pit_game_perfect_game")
    assert perfect is not None
    assert perfect.grade == "legendary"
    cg = milestones.get_by_key("pit_game_cg")
    assert cg is not None
    assert cg.grade == "uncommon"
    assert len(milestones.all_milestones) == 276
    ratio_keys = {
        item.key for item in milestones.all_milestones if item.scope == "season_ratio"
    }
    assert ratio_keys == set()


def test_game_scope_multi_hr_not_triggered_on_single_hr(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    game_ids = _import_games(aggregator, "game_box_13.html")
    achievements = checker.check_new_games(game_ids, season=2026)
    hr2 = [item for item in achievements if item.milestone.key == "bat_game_hr_2"]
    assert hr2 == []


def test_game_scope_multi_hr_triggered(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    if not (SAMPLES_BOX / "game_box_20.html").is_file():
        pytest.skip("game_box_20 sample missing")
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_20.html").parse()
    data.home_batting_notes = re.sub(
        r"K\. Tucker\s*\n\s*\(2, 5th Inning off R\. Nelson, 0 on, 0 outs\)",
        "K. Tucker 2 (5, 5th Inning off R. Nelson, 0 on, 0 outs)",
        data.home_batting_notes,
    )
    result = aggregator.import_boxscore(data, season=2026)
    assert result.error is None
    achievements = checker.check_new_games([data.meta.game_id], season=2026)
    hr2 = [item for item in achievements if item.milestone.key == "bat_game_hr_2"]
    assert len(hr2) >= 1
    assert any(item.player_name == "K. Tucker" for item in hr2)


def test_check_new_games_respects_tracked_teams(
    aggregator: Aggregator, milestones: MilestoneDefinitions
) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    game_ids = _import_games(aggregator, "game_box_13.html")
    all_checker = MilestoneChecker(aggregator, milestones, season_games_total=162)
    giants_checker = MilestoneChecker(
        aggregator,
        milestones,
        season_games_total=162,
        tracked_teams=["SF"],
    )
    all_achievements = all_checker.check_new_games(game_ids, season=2026)
    giants_achievements = giants_checker.check_new_games(game_ids, season=2026)

    giants_players = {item.player_id for item in giants_achievements if item.player_id}
    assert giants_players

    career500_all = [
        item for item in all_achievements if item.milestone.key == "bat_career_hr_500"
    ]
    career500_giants = [
        item for item in giants_achievements if item.milestone.key == "bat_career_hr_500"
    ]
    assert career500_all
    assert career500_giants == []


def test_career_scope_with_initial_stats(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    game_ids = _import_games(aggregator, "game_box_13.html")
    achievements = checker.check_new_games(game_ids, season=2026)
    career500 = [item for item in achievements if item.milestone.key == "bat_career_hr_500"]
    assert len(career500) == 1
    assert career500[0].player_id == 28987


def test_no_duplicate_career_record(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    InitialImporter(aggregator).import_batting(
        SAMPLES_STATS / "player_batting_stats.txt",
        "first_time",
        current_season=2026,
    )
    game_ids = _import_games(aggregator, "game_box_13.html", "game_box_14.html")
    first = checker.check_new_games([game_ids[0]], season=2026)
    checker.record_achievements(first)
    second = checker.check_new_games([game_ids[1]], season=2026)
    checker.record_achievements(second)
    rows = aggregator.conn.execute(
        """
        SELECT COUNT(*) AS cnt FROM milestone_records
        WHERE player_id = ? AND milestone_key = 'bat_career_hr_500'
        """,
        (28987,),
    ).fetchone()
    assert rows["cnt"] == 1


def test_complete_game_detection() -> None:
    meta = GameMeta(
        game_id=1,
        date="2026-04-01",
        away_team="Away",
        home_team="Home",
        away_score=0,
        home_score=1,
        away_hits=0,
        home_hits=5,
        away_errors=0,
        home_errors=0,
    )
    pitcher = PitcherLine(
        player_name="A. Pitcher",
        player_id=1,
        team="Home",
        decision="W",
        decision_record="(1-0)",
        ip=9.0,
        h=0,
        r=0,
        er=0,
        bb=0,
        k=10,
        hr=0,
        bf=27,
        pi=100,
        era=0.0,
    )
    data = BoxscoreData(
        meta=meta,
        away_batting=[],
        home_batting=[],
        away_pitching=[],
        home_pitching=[pitcher],
        away_batting_notes="",
        home_batting_notes="",
    )
    flags = detect_special_game(pitcher, [pitcher], meta, "Home", data)
    assert flags["is_cg"] == 1
    assert flags["is_sho"] == 1
    assert flags["is_no_hitter"] == 1
    assert flags["is_perfect_game"] == 1


def test_ratio_milestone_qualifier(aggregator: Aggregator) -> None:
    defs = MilestoneDefinitions(
        batting=[
            MilestoneDefinition(
                key="season_avg_400",
                label="시즌 4할",
                stat="season_avg",
                threshold=0.4,
                scope="season_ratio",
                category="batting",
            )
        ],
        pitching=[],
    )
    checker = MilestoneChecker(aggregator, defs, season_games_total=162)
    aggregator.conn.execute(
        """
        INSERT INTO players (player_id, full_name, short_name) VALUES (1, 'Test Player', 'T. Player')
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team, away_score, home_score,
            away_innings, home_innings
        ) VALUES (1, '2026-04-01', 2026, 'A', 'H', 1, 2, '[]', '[]')
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, season_hr, season_rbi
        ) VALUES (1, 1, 2026, 'H', '2026-04-01', 400, 200, 0, 0)
        """
    )
    achievements = checker.check_season_ratios(2026)
    assert achievements == []

    aggregator.conn.execute(
        "UPDATE batting_logs SET ab = 502, h = 201 WHERE player_id = 1 AND game_id = 1"
    )
    achievements = checker.check_season_ratios(2026)
    assert len(achievements) == 1
    assert achievements[0].current_value >= 0.4


def test_lower_direction_era(aggregator: Aggregator) -> None:
    defs = MilestoneDefinitions(
        batting=[],
        pitching=[
            MilestoneDefinition(
                key="season_era_200",
                label="시즌 2점대 ERA",
                stat="season_era",
                threshold=2.99,
                scope="season_ratio",
                category="pitching",
                direction="lower",
            )
        ],
    )
    checker = MilestoneChecker(aggregator, defs, season_games_total=162)
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (9, 'P Test', 'P. Test')"
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team, away_score, home_score,
            away_innings, home_innings
        ) VALUES (9, '2026-04-01', 2026, 'A', 'H', 1, 2, '[]', '[]')
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, er
        ) VALUES (9, 9, 2026, 'H', '2026-04-01', 486, 45)
        """
    )
    good = checker.check_season_ratios(2026)
    assert len(good) == 1

    aggregator.conn.execute(
        "UPDATE pitching_logs SET er = 60 WHERE player_id = 9 AND game_id = 9"
    )
    bad = checker.check_season_ratios(2026)
    assert bad == []


def test_season_ratio_only_best_milestone_recorded(aggregator: Aggregator) -> None:
    """시즌 비율 마일스톤은 가장 좋은 기록 하나만 반환해야 한다.

    타율 .430인 선수에게 .300/.350/.400 임계값이 모두 있을 때,
    가장 높은 .400 하나만 반환되어야 한다.
    """
    defs = MilestoneDefinitions(
        batting=[
            MilestoneDefinition(
                key="season_avg_300",
                label="시즌 타율 .300",
                stat="season_avg",
                threshold=0.300,
                scope="season_ratio",
                category="batting",
            ),
            MilestoneDefinition(
                key="season_avg_350",
                label="시즌 타율 .350",
                stat="season_avg",
                threshold=0.350,
                scope="season_ratio",
                category="batting",
            ),
            MilestoneDefinition(
                key="season_avg_400",
                label="시즌 타율 .400",
                stat="season_avg",
                threshold=0.400,
                scope="season_ratio",
                category="batting",
            ),
        ],
        pitching=[],
    )
    checker = MilestoneChecker(aggregator, defs, season_games_total=162)
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (7001, 'Kim Doyoung', 'D. Kim')"
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team, away_score, home_score,
            away_innings, home_innings
        ) VALUES (7001, '2026-09-30', 2026, 'A', 'H', 1, 2, '[]', '[]')
        """
    )
    # 502 타석 중 216안타 → 타율 .430
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, season_hr, season_rbi
        ) VALUES (7001, 7001, 2026, 'H', '2026-09-30', 502, 216, 0, 0)
        """
    )
    aggregator.conn.commit()

    achievements = checker.check_season_ratios(2026)
    # .300, .350, .400 모두 달성했지만 가장 높은 .400 하나만 반환해야 함
    assert len(achievements) == 1
    assert achievements[0].milestone.key == "season_avg_400"
    assert achievements[0].current_value >= 0.4


def test_season_ratio_lower_direction_only_best(aggregator: Aggregator) -> None:
    """ERA 등 낮을수록 좋은 마일스톤은 가장 낮은 임계값(가장 엄격한) 하나만 반환해야 한다."""
    defs = MilestoneDefinitions(
        batting=[],
        pitching=[
            MilestoneDefinition(
                key="season_era_350",
                label="시즌 ERA 3.50 이하",
                stat="season_era",
                threshold=3.50,
                scope="season_ratio",
                category="pitching",
                direction="lower",
            ),
            MilestoneDefinition(
                key="season_era_300",
                label="시즌 ERA 3.00 이하",
                stat="season_era",
                threshold=3.00,
                scope="season_ratio",
                category="pitching",
                direction="lower",
            ),
            MilestoneDefinition(
                key="season_era_250",
                label="시즌 ERA 2.50 이하",
                stat="season_era",
                threshold=2.50,
                scope="season_ratio",
                category="pitching",
                direction="lower",
            ),
        ],
    )
    checker = MilestoneChecker(aggregator, defs, season_games_total=162)
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (7002, 'Ace Pitcher', 'A. Pitcher')"
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team, away_score, home_score,
            away_innings, home_innings
        ) VALUES (7002, '2026-09-30', 2026, 'A', 'H', 0, 1, '[]', '[]')
        """
    )
    # 180이닝(540아웃), 자책점 40 → ERA = 40*9/180 = 2.00
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, er
        ) VALUES (7002, 7002, 2026, 'H', '2026-09-30', 540, 40)
        """
    )
    aggregator.conn.commit()

    achievements = checker.check_season_ratios(2026)
    # ERA 2.00은 3.50/3.00/2.50 모두 달성이지만, 가장 엄격한(낮은) 2.50 하나만 반환해야 함
    assert len(achievements) == 1
    assert achievements[0].milestone.key == "season_era_250"


def test_career_first_stats_from_zero(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    aggregator.conn.executemany(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (?, ?, ?)",
        [(9001, "Rookie Batter", "R. Batter"), (9002, "Rookie Pitcher", "R. Pitcher")],
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (900, '2026-04-01', 2026, 'Away', 'Home', 2, 3, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, rbi, home_runs, stolen_bases
        ) VALUES (900, 9001, 2026, 'Home', '2026-04-01', 4, 1, 1, 0, 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, h, bb, k, er,
            win, loss, save, hold, is_cg, is_sho, is_no_hitter, is_perfect_game
        ) VALUES (900, 9002, 2026, 'Home', '2026-04-01', 3, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0)
        """
    )
    aggregator.conn.commit()

    achievements = checker.check_new_games([900], season=2026)
    batter_keys = {
        item.milestone.key
        for item in achievements
        if item.player_id == 9001
    }
    pitcher_keys = {
        item.milestone.key
        for item in achievements
        if item.player_id == 9002
    }

    assert {
        "bat_career_first_games",
        "bat_career_first_hit",
        "bat_career_first_rbi",
        "bat_career_first_sb",
    } <= batter_keys
    assert {
        "pit_career_first_game",
        "pit_career_first_k",
        "pit_career_first_hold",
        "pit_career_first_save",
    } <= pitcher_keys
    assert "pit_career_first_win" not in pitcher_keys


def test_season_hr_milestone_detected_in_batch_import(
    aggregator: Aggregator, milestones: MilestoneDefinitions
) -> None:
    """Regression: season HR milestone missed when future games are already in DB.

    When all games are batch-imported before milestone checking begins,
    get_max_prior_season_stat must use game_id < ? (chronological order)
    rather than game_id <> ? (which would pick up later games' higher season_hr).
    """
    checker = MilestoneChecker(aggregator, milestones, season_games_total=162)
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (8001, 'HR Batter', 'H. Batter')"
    )
    # game_id=1001: player hits 20th HR (the milestone-crossing game)
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (1001, '2026-06-01', 2026, 'A', 'B', 1, 2, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, home_runs, season_hr
        ) VALUES (1001, 8001, 2026, 'B', '2026-06-01', 4, 1, 1, 20)
        """
    )
    # game_id=1002: later game where player has 25 HRs (already in DB)
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (1002, '2026-07-01', 2026, 'A', 'B', 1, 3, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, home_runs, season_hr
        ) VALUES (1002, 8001, 2026, 'B', '2026-07-01', 4, 2, 2, 25)
        """
    )
    aggregator.conn.commit()

    # Check both games at once (simulates batch import)
    achievements = checker.check_new_games([1001, 1002], season=2026)
    hr20 = [a for a in achievements if a.milestone.key == "bat_season_hr_20"]
    # Without the fix, prior = MAX(season_hr from games != 1001) = 25, so 25 < 20 → FALSE
    # With the fix,  prior = MAX(season_hr from games < 1001)  = None → 0.0, so 0 < 20 → TRUE
    assert len(hr20) == 1
    assert hr20[0].game_id == 1001


def test_season_hr_milestone_skipped_value_detected(
    aggregator: Aggregator, milestones: MilestoneDefinitions
) -> None:
    """시즌 40홈런 마일스톤: 39→41로 건너뛰어도 탐지돼야 한다."""
    checker = MilestoneChecker(aggregator, milestones, season_games_total=162)
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (8005, 'Skip Batter', 'S. Batter')"
    )
    # 이전 게임: season_hr = 39
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (3001, '2026-07-01', 2026, 'A', 'B', 1, 2, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, home_runs, season_hr
        ) VALUES (3001, 8005, 2026, 'B', '2026-07-01', 4, 1, 1, 39)
        """
    )
    # 마일스톤 게임: 한 게임에 2홈런 (39 → 41, 40 스킵)
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (3002, '2026-07-02', 2026, 'A', 'B', 1, 3, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, home_runs, season_hr
        ) VALUES (3002, 8005, 2026, 'B', '2026-07-02', 4, 2, 2, 41)
        """
    )
    aggregator.conn.commit()

    achievements = checker.check_new_games([3001, 3002], season=2026)
    hr40 = [a for a in achievements if a.milestone.key == "bat_season_hr_40" and a.player_id == 8005]
    # prior=39 < 40 <= 41=current → TRUE
    assert len(hr40) == 1, f"시즌 40홈런 미탐지 (achievements: {[a.milestone.key for a in achievements if a.player_id == 8005]})"
    assert hr40[0].game_id == 3002


def test_season_rbi_milestone_detected_in_batch_import(
    aggregator: Aggregator, milestones: MilestoneDefinitions
) -> None:
    """Regression: same batch-import bug for season_rbi milestones."""
    checker = MilestoneChecker(aggregator, milestones, season_games_total=162)
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (8002, 'RBI Batter', 'R. Batter')"
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (2001, '2026-06-01', 2026, 'A', 'B', 1, 2, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, rbi, season_rbi
        ) VALUES (2001, 8002, 2026, 'B', '2026-06-01', 4, 1, 2, 100)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (2002, '2026-07-01', 2026, 'A', 'B', 1, 3, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, rbi, season_rbi
        ) VALUES (2002, 8002, 2026, 'B', '2026-07-01', 4, 2, 5, 120)
        """
    )
    aggregator.conn.commit()

    achievements = checker.check_new_games([2001, 2002], season=2026)
    rbi100 = [a for a in achievements if a.milestone.key == "bat_season_rbi_100"]
    assert len(rbi100) == 1
    assert rbi100[0].game_id == 2001


def test_season_hits_milestone_detected_in_batch_import(
    aggregator: Aggregator, milestones: MilestoneDefinitions
) -> None:
    """Regression: season_h SUM 방식도 배치 임포트 시 정상 탐지돼야 한다."""
    checker = MilestoneChecker(aggregator, milestones, season_games_total=162)
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (8003, 'Hit Batter', 'H. Batter')"
    )
    # 마일스톤 게임: 2안타로 198 → 200
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (4001, '2026-07-01', 2026, 'A', 'B', 1, 2, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h
        ) VALUES (4001, 8003, 2026, 'B', '2026-07-01', 4, 2)
        """
    )
    # 미래 게임: 추가 안타 (이미 DB에 있음)
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (4002, '2026-08-01', 2026, 'A', 'B', 2, 3, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h
        ) VALUES (4002, 8003, 2026, 'B', '2026-08-01', 4, 30)
        """
    )
    aggregator.conn.commit()

    # game 4001이 첫 번째 게임이므로 prior=0, current=2 → 0 < 200은 안됨
    # game 4001 하나만 체크 시: prior=0, current=2 → 0 < 150 <= 2? NO → 올바름
    # 올바른 시나리오: game 4001이 198 → 200 지점이 되려면 이전 게임이 필요
    # game_id=3999 (이전 게임, 198안타)을 추가
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (3999, '2026-06-30', 2026, 'A', 'B', 1, 1, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h
        ) VALUES (3999, 8003, 2026, 'B', '2026-06-30', 4, 198)
        """
    )
    aggregator.conn.commit()

    # 배치: [4001, 4002] 체크 (4002는 이미 DB에 있는 미래 게임)
    achievements = checker.check_new_games([4001, 4002], season=2026)
    hit200 = [a for a in achievements if a.milestone.key == "bat_season_hits_200" and a.player_id == 8003]
    # prior(game<4001) = 198, current = 198+2 = 200 → 198 < 200 <= 200 → TRUE
    assert len(hit200) == 1
    assert hit200[0].game_id == 4001


def test_season_k_milestone_detected_in_batch_import(
    aggregator: Aggregator, milestones: MilestoneDefinitions
) -> None:
    """Regression: season_k_pit SUM 방식도 배치 임포트 시 정상 탐지."""
    checker = MilestoneChecker(aggregator, milestones, season_games_total=162)
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (8004, 'K Pitcher', 'K. Pitcher')"
    )
    # game_id=5001: 탈삼진 마일스톤 게임 (이전까지 197K, 이 게임에 3K → 200)
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (5001, '2026-07-01', 2026, 'A', 'B', 1, 2, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, k
        ) VALUES (5001, 8004, 2026, 'B', '2026-07-01', 21, 3)
        """
    )
    # game_id=4999: 이전 게임 (197K)
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (4999, '2026-06-30', 2026, 'A', 'B', 1, 1, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, k
        ) VALUES (4999, 8004, 2026, 'B', '2026-06-30', 21, 197)
        """
    )
    # game_id=5002: 미래 게임 (이미 DB에 있음, 추가 30K)
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (5002, '2026-08-01', 2026, 'A', 'B', 2, 3, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO pitching_logs (
            game_id, player_id, season, team, date, ip_outs, k
        ) VALUES (5002, 8004, 2026, 'B', '2026-08-01', 21, 30)
        """
    )
    aggregator.conn.commit()

    achievements = checker.check_new_games([5001, 5002], season=2026)
    k200 = [a for a in achievements if a.milestone.key == "pit_season_k_200" and a.player_id == 8004]
    # prior(games < 5001) = 197, current = 197+3 = 200 → 197 < 200 <= 200 → TRUE
    assert len(k200) == 1
    assert k200[0].game_id == 5001


def test_career_first_stat_not_retriggered_with_prior_init(
    aggregator: Aggregator, checker: MilestoneChecker
) -> None:
    aggregator.conn.execute(
        "INSERT INTO players (player_id, full_name, short_name) VALUES (9003, 'Vet', 'V. Vet')"
    )
    aggregator.conn.execute(
        """
        INSERT INTO career_batting_init (
            player_id, season, g, ab, h, hr, rbi, bb, k, doubles, triples, sb, r
        ) VALUES (9003, 2025, 10, 30, 5, 0, 2, 1, 8, 1, 0, 0, 1)
        """
    )
    set_meta(aggregator.conn, "init_season_coverage", "2025")
    aggregator.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team,
            away_score, home_score, away_innings, home_innings, is_mlb
        ) VALUES (901, '2026-04-02', 2026, 'Away', 'Home', 1, 2, '[]', '[]', 1)
        """
    )
    aggregator.conn.execute(
        """
        INSERT INTO batting_logs (
            game_id, player_id, season, team, date, ab, h, rbi, home_runs, stolen_bases
        ) VALUES (901, 9003, 2026, 'Home', '2026-04-02', 3, 1, 0, 0, 0)
        """
    )
    aggregator.conn.commit()

    achievements = checker.check_new_games([901], season=2026)
    first_keys = {
        item.milestone.key
        for item in achievements
        if item.player_id == 9003 and item.milestone.key.startswith("bat_career_first_")
    }
    assert first_keys == set()

