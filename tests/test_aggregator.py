"""Aggregator and batting notes tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.parser.batting_notes import get_player_event_counts
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.stats.ip_utils import ip_to_outs, outs_to_ip_str

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_records.db"


@pytest.fixture
def aggregator(db_path: Path) -> Aggregator:
    agg = Aggregator(db_path)
    yield agg
    agg.close()


def test_context_manager_rolls_back_on_error(db_path: Path) -> None:
    with pytest.raises(RuntimeError):
        with Aggregator(db_path) as agg:
            agg.conn.execute(
                "INSERT INTO players (player_id, full_name, short_name) "
                "VALUES (1, 'Test Player', 'T. Player')"
            )
            raise RuntimeError("force rollback")

    with Aggregator(db_path) as agg:
        assert agg.conn.execute(
            "SELECT 1 FROM players WHERE player_id = 1"
        ).fetchone() is None


def test_ip_conversion() -> None:
    assert ip_to_outs("2.1") == 7
    assert ip_to_outs("4.0") == 12
    assert ip_to_outs("0.2") == 2
    assert outs_to_ip_str(7) == "2.1"


def test_batting_notes_counts() -> None:
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    grichuk = get_player_event_counts(data.away_batting_notes, "R. Grichuk")
    assert grichuk.home_runs == 1

    lee = get_player_event_counts(data.home_batting_notes, "J. Lee")
    assert lee.doubles == 1
    assert lee.home_runs == 1
    assert lee.stolen_bases == 1

    mcmahon = get_player_event_counts(data.away_batting_notes, "R. McMahon")
    assert mcmahon.gidp == 1

    game20 = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_20.html").parse()
    tucker = get_player_event_counts(game20.home_batting_notes, "K. Tucker")
    assert tucker.home_runs == 1

    from core.parser.batting_notes import parse_team_batting_notes

    sb_counts = parse_team_batting_notes("BATTING\nSB:\nJ. Lee 3 (15)\n")
    assert sb_counts["J. Lee"].stolen_bases == 3

    hr_counts = parse_team_batting_notes(
        "BATTING\nHome Runs:\nR. Grichuk 2 (5, 6th Inning off P. Blackburn, 1 on, 1 out)\n"
    )
    assert hr_counts["R. Grichuk"].home_runs == 2


def test_import_boxscore(aggregator: Aggregator) -> None:
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    result = aggregator.import_boxscore(data, season=2026)
    assert result.skipped is False
    assert result.error is None
    assert aggregator.game_exists(13)

    grichuk = aggregator.conn.execute(
        """
        SELECT home_runs, doubles, stolen_bases, gidp
        FROM batting_logs
        WHERE game_id = 13 AND player_id = 28987
        """
    ).fetchone()
    assert grichuk["home_runs"] == 1

    schlittler = aggregator.conn.execute(
        """
        SELECT ip_outs, decision, loss, game_score
        FROM pitching_logs
        WHERE game_id = 13 AND player_id = 50432
        """
    ).fetchone()
    assert schlittler["ip_outs"] == 7
    assert schlittler["decision"] == "L"
    assert schlittler["loss"] == 1
    assert schlittler["game_score"] == 23


def test_import_skips_duplicate(aggregator: Aggregator) -> None:
    data = BoxscoreHTMLParser(SAMPLES_BOX / "game_box_13.html").parse()
    aggregator.import_boxscore(data, season=2026)
    again = aggregator.import_boxscore(data, season=2026)
    assert again.skipped is True


def test_import_all_new(aggregator: Aggregator) -> None:
    result = aggregator.import_all_new(SAMPLES_BOX, season=2026)
    assert result.total_scanned >= 8
    assert result.imported >= 2
    assert result.candidates >= 2

    again = aggregator.import_all_new(SAMPLES_BOX, season=2026)
    assert again.imported == 0
    assert again.skipped_existing == result.total_scanned
    assert again.candidates == 0


def test_import_mlb_only_filter(aggregator: Aggregator, tmp_path: Path) -> None:
    mlb = tmp_path / "game_box_90001.html"
    mlb.write_bytes((SAMPLES_BOX / "game_box_13.html").read_bytes())
    wbc = tmp_path / "game_box_90002.html"
    wbc.write_text(
        "<html><head><title>WBC Box Score, Korea at Japan</title></head></html>",
        encoding="utf-8",
    )

    mlb_only = aggregator.import_all_new(tmp_path, season=2026, mlb_only=True)
    assert mlb_only.imported == 1
    assert mlb_only.skipped_non_mlb == 1

    # Second run: both files are now cached in processed_boxscores — no I/O for either.
    again = aggregator.import_all_new(tmp_path, season=2026, mlb_only=True)
    assert again.imported == 0
    assert again.skipped_existing == 2   # MLB game + non-MLB file both cached
    assert again.skipped_non_mlb == 0   # not re-peeked


def test_import_cache_skips_all_on_second_run(aggregator: Aggregator) -> None:
    result = aggregator.import_all_new(SAMPLES_BOX, season=2026)
    first_scanned = result.total_scanned
    assert first_scanned > 0

    again = aggregator.import_all_new(SAMPLES_BOX, season=2026)
    assert again.imported == 0
    assert again.skipped_existing == first_scanned
    assert again.skipped_mtime == 0


def test_reimport_boxscore_file(aggregator: Aggregator) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    data = BoxscoreHTMLParser(path).parse()
    first = aggregator.import_boxscore(data, season=2026)
    assert first.skipped is False

    row = aggregator.conn.execute(
        "SELECT home_runs FROM batting_logs WHERE game_id = 13 AND player_id = 28987"
    ).fetchone()
    assert row["home_runs"] == 1

    aggregator.conn.execute(
        """
        UPDATE batting_logs SET home_runs = 99
        WHERE game_id = 13 AND player_id = 28987
        """
    )
    aggregator.conn.commit()

    result = aggregator.reimport_boxscore_file(path, season=2026)
    assert result.error is None
    assert result.skipped is False
    assert result.replaced is True

    row = aggregator.conn.execute(
        "SELECT home_runs FROM batting_logs WHERE game_id = 13 AND player_id = 28987"
    ).fetchone()
    assert row["home_runs"] == 1


def test_reimport_parse_failure_preserves_existing_game(
    aggregator: Aggregator, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    aggregator.import_boxscore(BoxscoreHTMLParser(path).parse(), season=2026)

    def fail_parse(_self):
        raise RuntimeError("malformed replacement")

    monkeypatch.setattr(BoxscoreHTMLParser, "parse", fail_parse)
    result = aggregator.reimport_boxscore_file(path, season=2026)

    assert result.error == "malformed replacement"
    assert aggregator.game_exists(13)
    assert aggregator.conn.execute(
        "SELECT COUNT(*) FROM batting_logs WHERE game_id = 13"
    ).fetchone()[0] > 0


def test_reimport_spring_training_preserves_existing_game(
    aggregator: Aggregator, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    aggregator.import_boxscore(BoxscoreHTMLParser(path).parse(), season=2026)
    replacement = BoxscoreHTMLParser(path).parse()
    replacement.meta.is_spring_training = True
    monkeypatch.setattr(BoxscoreHTMLParser, "parse", lambda _self: replacement)

    result = aggregator.reimport_boxscore_file(path, season=2026)

    assert result.error == "Spring training boxscore is not tracked."
    assert aggregator.game_exists(13)
    assert aggregator.conn.execute(
        "SELECT COUNT(*) FROM batting_logs WHERE game_id = 13"
    ).fetchone()[0] > 0


def test_reimport_insert_failure_rolls_back_deleted_data(
    aggregator: Aggregator, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    aggregator.import_boxscore(BoxscoreHTMLParser(path).parse(), season=2026)
    before = aggregator.conn.execute(
        "SELECT COUNT(*) FROM batting_logs WHERE game_id = 13"
    ).fetchone()[0]

    def fail_insert(*_args, **_kwargs):
        raise RuntimeError("insertion failed")

    monkeypatch.setattr(aggregator, "_insert_game", fail_insert)
    result = aggregator.reimport_boxscore_file(path, season=2026)

    assert result.error == "insertion failed"
    assert aggregator.game_exists(13)
    assert aggregator.conn.execute(
        "SELECT COUNT(*) FROM batting_logs WHERE game_id = 13"
    ).fetchone()[0] == before


def test_reimport_cross_season_uses_the_matching_synthetic_game(
    aggregator: Aggregator,
) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    first = aggregator.reimport_boxscore_file(path, season=2026)
    second = aggregator.reimport_boxscore_file(path, season=2027)
    assert first.game_id == 13
    assert second.game_id != 13

    replacement = aggregator.reimport_boxscore_file(path, season=2027)
    assert replacement.error is None
    assert replacement.game_id == second.game_id
    rows = aggregator.conn.execute(
        "SELECT game_id, season FROM games ORDER BY season"
    ).fetchall()
    assert [(row["game_id"], row["season"]) for row in rows] == [
        (13, 2026),
        (second.game_id, 2027),
    ]


def test_past_reimport_is_rejected_without_any_database_change(
    aggregator: Aggregator,
) -> None:
    for game_id in (13, 14):
        path = SAMPLES_BOX / f"game_box_{game_id}.html"
        aggregator.import_boxscore(BoxscoreHTMLParser(path).parse(), season=2026)
    before = aggregator.conn.serialize()

    result = aggregator.reimport_boxscore_file(
        SAMPLES_BOX / "game_box_13.html", season=2026
    )

    assert result.error is not None
    assert "full-season reprocessing" in result.error
    assert aggregator.conn.serialize() == before


def test_same_date_higher_id_reimport_is_also_rejected_without_changes(
    aggregator: Aggregator, tmp_path: Path
) -> None:
    for game_id in (13, 14):
        target = tmp_path / f"game_box_{game_id}.html"
        target.write_bytes(
            (SAMPLES_BOX / f"game_box_{game_id}.html").read_bytes()
        )
    aggregator.import_all_new(tmp_path, season=2026)
    path = tmp_path / "game_box_14.html"
    stored_mtime = aggregator.conn.execute(
        "SELECT mtime FROM processed_boxscores WHERE filename = ?", (path.name,)
    ).fetchone()[0]
    before = aggregator.conn.serialize()

    result = aggregator.reimport_boxscore_file(path, season=2026)

    assert result.error is not None
    assert "same-date ambiguous" in result.error
    assert aggregator.conn.serialize() == before
    assert aggregator.conn.execute(
        "SELECT mtime FROM processed_boxscores WHERE filename = ?", (path.name,)
    ).fetchone()[0] == stored_mtime


def test_latest_reimport_can_be_rolled_back_after_downstream_failure(
    aggregator: Aggregator,
) -> None:
    path = SAMPLES_BOX / "game_box_14.html"
    aggregator.import_boxscore(BoxscoreHTMLParser(path).parse(), season=2026)
    player_id = aggregator.conn.execute(
        "SELECT player_id FROM batting_logs WHERE game_id = 14 LIMIT 1"
    ).fetchone()[0]
    aggregator.conn.execute(
        """
        INSERT INTO milestone_records (
            player_id, milestone_key, milestone_label, scope, season, game_id,
            achieved_date, achieved_value, is_manual
        ) VALUES (?, 'generated_before', 'Generated', 'game', 2026, 14,
                  '2026-03-27', 1, 0)
        """,
        (player_id,),
    )
    aggregator.conn.commit()
    before = aggregator.conn.serialize()

    result = aggregator.reimport_boxscore_file(path, season=2026, commit=False)
    assert result.error is None
    assert aggregator.conn.in_transaction
    # Simulate a downstream milestone/streak failure before the owner commit.
    aggregator.conn.rollback()

    assert aggregator.conn.serialize() == before


def test_reimport_commit_false_does_not_commit_an_outer_transaction(
    aggregator: Aggregator,
) -> None:
    path = SAMPLES_BOX / "game_box_14.html"
    aggregator.import_boxscore(BoxscoreHTMLParser(path).parse(), season=2026)
    aggregator.conn.execute("BEGIN")
    aggregator.conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('outer_marker', '1')"
    )

    result = aggregator.reimport_boxscore_file(path, season=2026, commit=False)

    assert result.error is None
    assert aggregator.conn.in_transaction
    aggregator.conn.rollback()
    assert aggregator.conn.execute(
        "SELECT value FROM db_meta WHERE key = 'outer_marker'"
    ).fetchone() is None
    assert aggregator.game_exists(14)


def test_reimport_commit_true_is_rejected_inside_outer_transaction(
    aggregator: Aggregator,
) -> None:
    path = SAMPLES_BOX / "game_box_14.html"
    aggregator.import_boxscore(BoxscoreHTMLParser(path).parse(), season=2026)
    aggregator.conn.execute("BEGIN")
    aggregator.conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('outer_marker', '1')"
    )

    result = aggregator.reimport_boxscore_file(path, season=2026)

    assert result.error is not None
    assert "commit=False" in result.error
    assert aggregator.conn.in_transaction
    aggregator.conn.rollback()
    assert aggregator.conn.execute(
        "SELECT value FROM db_meta WHERE key = 'outer_marker'"
    ).fetchone() is None


def test_reimport_preserves_manual_milestone(aggregator: Aggregator) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    aggregator.reimport_boxscore_file(path, season=2026)
    player_id = aggregator.conn.execute(
        "SELECT player_id FROM batting_logs WHERE game_id = 13 LIMIT 1"
    ).fetchone()[0]
    aggregator.conn.execute(
        """
        INSERT INTO milestone_records (
            player_id, milestone_key, milestone_label, scope, season, game_id,
            achieved_date, achieved_value, is_manual
        ) VALUES (?, 'manual_test', 'Manual', 'game', 2026, 13,
                  '2026-01-01', 1, 1)
        """,
        (player_id,),
    )
    aggregator.conn.commit()

    assert aggregator.reimport_boxscore_file(path, season=2026).error is None
    assert aggregator.conn.execute(
        "SELECT COUNT(*) FROM milestone_records WHERE milestone_key = 'manual_test'"
    ).fetchone()[0] == 1


def test_processed_placeholder_becoming_regular_is_classified_as_imported(
    aggregator: Aggregator, tmp_path: Path
) -> None:
    path = tmp_path / "game_box_13.html"
    path.write_bytes((SAMPLES_BOX / "game_box_13.html").read_bytes())
    old_mtime = path.stat().st_mtime - 2.0
    aggregator.conn.execute(
        """
        INSERT INTO processed_boxscores (filename, game_id, mtime, is_mlb)
        VALUES (?, 13, ?, 0)
        """,
        (path.name, old_mtime),
    )
    aggregator.conn.commit()

    result = aggregator.import_all_new(tmp_path, season=2026)

    assert result.imported == 1
    assert result.imported_game_ids == [13]
    assert result.refreshed_game_ids == []


def test_batch_rewrite_is_deferred_without_updating_data_or_mtime(
    aggregator: Aggregator, tmp_path: Path
) -> None:
    for game_id in (13, 14):
        target = tmp_path / f"game_box_{game_id}.html"
        target.write_bytes(
            (SAMPLES_BOX / f"game_box_{game_id}.html").read_bytes()
        )
    aggregator.import_all_new(tmp_path, season=2026)
    path = tmp_path / "game_box_13.html"
    stored_mtime = aggregator.conn.execute(
        "SELECT mtime FROM processed_boxscores WHERE filename = ?", (path.name,)
    ).fetchone()[0]
    changed_mtime = float(stored_mtime) + 2.0
    os.utime(path, (changed_mtime, changed_mtime))
    before = aggregator.conn.serialize()

    result = aggregator.import_all_new(tmp_path, season=2026)

    assert len(result.errors) == 1
    assert "safe single-game re-import" in str(result.errors[0].error)
    assert result.refreshed_game_ids == []
    assert aggregator.conn.serialize() == before
    assert aggregator.conn.execute(
        "SELECT mtime FROM processed_boxscores WHERE filename = ?", (path.name,)
    ).fetchone()[0] == stored_mtime


def test_reimport_recalculates_positions_for_removed_batters(
    aggregator: Aggregator, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    first = BoxscoreHTMLParser(path).parse()
    aggregator.import_boxscore(first, season=2026)
    removed_id = first.away_batting[0].player_id
    assert aggregator.conn.execute(
        "SELECT primary_position FROM players WHERE player_id = ?", (removed_id,)
    ).fetchone()[0]

    replacement = BoxscoreHTMLParser(path).parse()
    replacement.away_batting = [
        batter for batter in replacement.away_batting
        if batter.player_id != removed_id
    ]
    monkeypatch.setattr(BoxscoreHTMLParser, "parse", lambda _self: replacement)
    assert aggregator.reimport_boxscore_file(path, season=2026).error is None

    assert aggregator.conn.execute(
        "SELECT primary_position FROM players WHERE player_id = ?", (removed_id,)
    ).fetchone()[0] == ""


def test_delete_game_import_data(aggregator: Aggregator) -> None:
    path = SAMPLES_BOX / "game_box_13.html"
    data = BoxscoreHTMLParser(path).parse()
    aggregator.import_boxscore(data, season=2026)
    assert aggregator.delete_game_import_data(13) is True
    assert not aggregator.game_exists(13)
    assert aggregator.delete_game_import_data(13) is False


def test_summarize_boxscore_file() -> None:
    from core.parser.boxscore_html import summarize_boxscore_file

    summary = summarize_boxscore_file(SAMPLES_BOX / "game_box_13.html")
    assert summary is not None
    assert summary.game_id == 13
    assert summary.is_mlb is True
    assert summary.away_team
    assert summary.home_team
    assert summary.date


def test_season_aggregation(aggregator: Aggregator) -> None:
    for path in (SAMPLES_BOX / "game_box_13.html", SAMPLES_BOX / "game_box_14.html"):
        aggregator.import_boxscore(BoxscoreHTMLParser(path).parse(), season=2026)

    chisholm = aggregator.get_batting_season(1259, 2026)
    assert chisholm is not None
    assert chisholm["ab"] >= 5

    career = aggregator.get_batting_career(1259)
    assert career is not None
    assert career["career_ab"] >= 5

    totals = aggregator.get_season_batting_totals(2026)
    assert len(totals) > 0
