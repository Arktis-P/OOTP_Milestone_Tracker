"""MLB-only box score stats aggregation."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


@pytest.fixture
def aggregator(tmp_path: Path) -> Aggregator:
    db_path = tmp_path / "mlb.db"
    with Aggregator(db_path) as agg:
        data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
        agg.import_boxscore(data, season=2026, is_mlb=True)
        conn = agg.conn
        conn.execute(
            """
            INSERT INTO games (
                game_id, date, season, away_team, home_team,
                away_score, home_score, away_innings, home_innings,
                away_hits, home_hits, away_errors, home_errors,
                ballpark, attendance, game_time, weather,
                player_of_game_id, player_of_game_name, special_notes, is_mlb
            ) VALUES (
                99999, '2026-03-05', 2026, 'Korea', 'Japan',
                0, 0, '[]', '[]',
                0, 0, 0, 0,
                '', 0, '', '',
                NULL, '', '', 0
            )
            """
        )
        conn.execute(
            """
            INSERT INTO batting_logs (
                game_id, player_id, season, team, date,
                ab, r, h, rbi, bb, k, lob,
                season_avg, season_hr, season_rbi,
                doubles, triples, home_runs, stolen_bases, hit_by_pitch, gidp
            ) VALUES (
                99999, 28987, 2026, 'Korea', '2026-03-05',
                4, 1, 2, 1, 0, 0, 0,
                0.500, 0, 0,
                0, 0, 0, 0, 0, 0
            )
            """
        )
        conn.commit()
        yield agg


def test_season_stats_exclude_non_mlb_games(aggregator: Aggregator) -> None:
    logs = aggregator.get_player_batting_game_logs(28987, 2026)
    assert len(logs) == 1
    assert logs[0]["opponent"] != "Japan"

    season = aggregator.get_batting_season(28987, 2026)
    assert season is not None
    assert int(season["ab"]) == int(logs[0]["ab"])
