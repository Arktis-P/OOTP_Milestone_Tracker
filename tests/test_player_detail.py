from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from core.config import AppSettings
from core.milestone.definitions import MilestoneDefinition, MilestoneDefinitions
from core.stats.aggregator import Aggregator
from core.stats.player_detail import classify_player_event, load_player_detail
from gui.views.stats_view import StatsView


def _defs() -> MilestoneDefinitions:
    return MilestoneDefinitions(
        batting=[
            MilestoneDefinition(
                key="bat_career_hr_500",
                label="500 HR",
                stat="career_hr",
                threshold=500,
                scope="career",
                category="batting",
                grade="legendary",
                near_n=10,
            ),
            MilestoneDefinition(
                key="bat_season_award_mvp",
                label="MVP",
                stat="award_mvp",
                threshold=1,
                scope="season",
                category="batting",
                direction="boolean",
                grade="epic",
            ),
        ],
        pitching=[],
        team=[
            MilestoneDefinition(
                key="team_game_hits_20",
                label="Team 20 Hits",
                stat="team_hits",
                threshold=20,
                scope="team_game",
                category="team",
            )
        ],
    )


def _settings() -> AppSettings:
    return AppSettings(current_season=2026, season_games_total=162)


def _player(agg: Aggregator, player_id: int = 7) -> dict:
    row = agg.conn.execute(
        """
        SELECT player_id, full_name, short_name, primary_position
        FROM players
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()
    return dict(row)


def _insert_game(agg: Aggregator, game_id: int, season: int, date: str) -> None:
    agg.conn.execute(
        """
        INSERT INTO games (
            game_id, date, season, away_team, home_team, away_score, home_score,
            away_innings, home_innings, is_mlb
        ) VALUES (?, ?, ?, 'SEA', 'NYY', 1, 2, '', '', 1)
        """,
        (game_id, date, season),
    )


def test_event_classification_read_model_and_team_records_excluded(tmp_path: Path) -> None:
    agg = Aggregator(tmp_path / "detail-events.db")
    try:
        defs = _defs()
        agg.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name, primary_position)
            VALUES (7, 'Test Player', 'T. Player', 'CF')
            """
        )
        agg.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name)
            VALUES (0, 'Team Record', 'Team Record')
            """
        )
        rows = [
            (7, "bat_career_hr_500", "500 HR", "career", 2026, 11, "2026-05-01", "", None),
            (7, "bat_season_award_mvp", "MVP", "season", 2026, None, "2026-06-01", "", None),
            (7, "manual_transfer_trade", "Trade", "manual_event", 2026, None, "2026-07-01", "SEA", "deal"),
            (7, "manual_injury", "Injury", "manual_event", 2026, None, "2026-08-01", "SEA", "day to day"),
            (7, "team_game_hits_20", "Team 20 Hits", "team_game", 2026, 22, "2026-09-01", "SEA", ""),
            (0, "team_game_hits_20", "Team 20 Hits", "team_game", 2026, 22, "2026-09-01", "SEA", ""),
        ]
        agg.conn.executemany(
            """
            INSERT INTO milestone_records (
                player_id, milestone_key, milestone_label, scope, season, game_id,
                achieved_date, achieved_value, team, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            rows,
        )
        agg.conn.commit()

        assert classify_player_event(
            {"milestone_key": "manual_transfer_trade", "scope": "manual_event"},
            None,
        ) == "transfer"

        detail = load_player_detail(agg, defs, _settings(), _player(agg), season=2026)
        kinds = [event.kind for event in detail.events]

        assert kinds == ["injury", "transfer", "award", "milestone"]
        assert all(event.label != "Team 20 Hits" for event in detail.events)
    finally:
        agg.close()


def test_current_team_falls_back_to_player_affiliation(tmp_path: Path) -> None:
    agg = Aggregator(tmp_path / "detail-affiliation.db")
    try:
        agg.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name, primary_position)
            VALUES (7, 'Test Player', 'T. Player', 'CF')
            """
        )
        agg.conn.execute(
            """
            INSERT INTO player_team_affiliations (
                player_id, season, team_abbr, team_name
            ) VALUES (7, 2026, 'SEA', 'Seattle Mariners')
            """
        )
        agg.conn.commit()

        detail = load_player_detail(agg, _defs(), _settings(), _player(agg), season=2026)

        assert detail.current_team == "SEA"
    finally:
        agg.close()


def test_active_streak_display_for_selected_player_only(tmp_path: Path) -> None:
    agg = Aggregator(tmp_path / "detail-streaks.db")
    try:
        agg.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name)
            VALUES (7, 'Test Player', 'T. Player')
            """
        )
        agg.conn.executemany(
            """
            INSERT INTO player_streak_state (
                season, player_id, streak_type, current_value, ip_outs_accum,
                first_success_game_date, last_success_game_date
            ) VALUES (2026, ?, ?, ?, ?, '2026-04-01', '2026-04-10')
            """,
            [
                (7, "hit_streak", 12, 0),
                (8, "hit_streak", 99, 0),
            ],
        )
        agg.conn.commit()

        detail = load_player_detail(agg, _defs(), _settings(), _player(agg), season=2026)

        assert len(detail.active_streaks) == 1
        assert detail.active_streaks[0].display_value == "12"
        assert detail.active_streaks[0].unit == "games"
    finally:
        agg.close()


def test_missing_streak_policy_falls_back_to_raw_display(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.stats import player_detail

    agg = Aggregator(tmp_path / "detail-missing-policy.db")
    try:
        agg.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name)
            VALUES (7, 'Test Player', 'T. Player')
            """
        )
        agg.conn.execute(
            """
            INSERT INTO player_streak_state (
                season, player_id, streak_type, current_value,
                first_success_game_date, last_success_game_date
            ) VALUES (2026, 7, 'custom_streak', 4, '2026-04-01', '2026-04-10')
            """
        )
        agg.conn.commit()
        monkeypatch.setattr(
            player_detail,
            "load_streak_policies",
            lambda: (_ for _ in ()).throw(OSError("missing")),
        )

        detail = load_player_detail(agg, _defs(), _settings(), _player(agg), season=2026)

        assert detail.active_streaks[0].label == "custom_streak"
        assert detail.active_streaks[0].display_value == "4"
    finally:
        agg.close()


def test_cached_next_milestones_use_store_order_without_seeding(tmp_path: Path) -> None:
    agg = Aggregator(tmp_path / "detail-predictions.db")
    try:
        defs = _defs()
        agg.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name)
            VALUES (7, 'Test Player', 'T. Player')
            """
        )
        agg.conn.executemany(
            """
            INSERT INTO milestone_predictions (
                player_id, milestone_key, season, player_name, milestone_label,
                grade, current_value, threshold, remaining, progress_pct, season_note
            ) VALUES (7, ?, 2026, 'Test Player', ?, ?, ?, ?, ?, ?, 'pre_season')
            """,
            [
                ("bat_career_hr_500", "500 HR", "legendary", 499, 500, 1, 99.8),
                ("legacy_far", "Far", "common", 10, 100, 90, 10.0),
            ],
        )
        agg.conn.commit()

        detail = load_player_detail(agg, defs, _settings(), _player(agg), season=2026)

        assert [item.milestone_key for item in detail.next_milestones] == [
            "bat_career_hr_500",
            "legacy_far",
        ]
        assert detail.next_milestones[0].is_near is True
    finally:
        agg.close()


def test_empty_and_missing_player_are_actionable(tmp_path: Path) -> None:
    agg = Aggregator(tmp_path / "detail-empty.db")
    try:
        assert load_player_detail(agg, _defs(), _settings(), None, season=2026).status == "select_player"
        missing = {"player_id": 404, "primary_position": "SS"}
        assert load_player_detail(agg, _defs(), _settings(), missing, season=2026).status == "missing_player"
        agg.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name)
            VALUES (7, 'Test Player', 'T. Player')
            """
        )
        agg.conn.commit()
        assert load_player_detail(agg, _defs(), _settings(), _player(agg), season=2026).status == "empty_detail"
    finally:
        agg.close()


def test_detail_refreshes_across_stats_view_season_selection(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    agg = Aggregator(tmp_path / "detail-view.db")
    try:
        agg.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name, primary_position)
            VALUES (7, 'Test Player', 'T. Player', 'RF')
            """
        )
        agg.conn.execute(
            """
            INSERT INTO players (player_id, full_name, short_name, primary_position)
            VALUES (8, 'Other Player', 'O. Player', 'SP')
            """
        )
        _insert_game(agg, 101, 2025, "2025-04-01")
        _insert_game(agg, 102, 2026, "2026-04-01")
        _insert_game(agg, 103, 2026, "2026-04-02")
        agg.conn.executemany(
            """
            INSERT INTO batting_logs (
                game_id, player_id, season, team, date, ab, r, h, rbi, bb, k
            ) VALUES (?, 7, ?, ?, ?, 4, 1, 1, 1, 0, 1)
            """,
            [
                (101, 2025, "NYY", "2025-04-01"),
                (102, 2026, "SEA", "2026-04-01"),
            ],
        )
        agg.conn.execute(
            """
            INSERT INTO pitching_logs (
                game_id, player_id, season, team, date, ip_outs, h, r, er, bb, k, hr
            ) VALUES (103, 8, 2026, 'BOS', '2026-04-02', 18, 4, 2, 2, 1, 6, 1)
            """
        )
        agg.conn.commit()

        view = StatsView(agg, _settings(), _defs())
        qapp.processEvents()

        assert view.focus_player(7) is True
        qapp.processEvents()
        assert "SEA" in view.player_detail_summary.meta_label.text()
        index_2025 = view.season_combo.findData(2025)
        assert index_2025 >= 0
        view.season_combo.setCurrentIndex(index_2025)
        qapp.processEvents()

        assert "NYY" in view.player_detail_summary.meta_label.text()
        assert "2025" in view.player_detail_summary.meta_label.text()

        index_2026 = view.season_combo.findData(2026)
        assert index_2026 >= 0
        view.season_combo.setCurrentIndex(index_2026)
        assert view.focus_player(8) is True
        qapp.processEvents()

        assert "BOS" in view.player_detail_summary.meta_label.text()
        assert "2026" in view.player_detail_summary.meta_label.text()
    finally:
        agg.close()


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])
