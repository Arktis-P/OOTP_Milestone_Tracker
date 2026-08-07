from __future__ import annotations

import json
import sqlite3
from argparse import Namespace
from datetime import date
from pathlib import Path

import pytest
import scripts.replay_recent_window as replay

from core.stats.aggregator import Aggregator
from core.milestone.checker import MilestoneChecker
from core.milestone.definitions import load_milestones
from scripts.replay_recent_window import (
    RecentReplayConfig,
    ReplayPathError,
    _clear_window,
    _clear_window_source_state,
    _config_from_args,
    _apply_ready_messages,
    _default_messages_dir,
    _replace_with_retry,
    determine_window,
    run_recent_replay,
    subtract_calendar_month,
    verify_backup,
)


def _db(path: Path) -> None:
    with Aggregator(path) as agg:
        conn = agg.conn
        conn.execute("INSERT INTO players (player_id, full_name) VALUES (1, 'Player')")
        for game_id, when in ((1, "2026-04-01"), (2, "2026-05-15")):
            conn.execute("INSERT INTO games (game_id,date,season,away_team,home_team,away_score,home_score,away_innings,home_innings,is_mlb) VALUES (?,?,?,?,?,?,?,?,?,1)", (game_id, when, 2026, "A", "B", 1, 0, "", ""))
            conn.execute("INSERT INTO batting_logs (game_id,player_id,season,team,date) VALUES (?,?,?,?,?)", (game_id, 1, 2026, "A", when))
        conn.execute("INSERT INTO milestone_records (player_id,milestone_key,milestone_label,scope,season,game_id,achieved_date,achieved_value,source,is_manual) VALUES (1,'auto','Auto','game',2026,2,'2026-05-15',1,'boxscore_auto',0)")
        conn.execute("INSERT INTO milestone_records (player_id,milestone_key,milestone_label,scope,season,game_id,achieved_date,achieved_value,source,is_manual) VALUES (1,'manual','Manual','game',2026,2,'2026-05-15',1,'manual',1)")
        conn.commit()


def test_month_math_and_window_uses_latest_game(tmp_path: Path) -> None:
    db = tmp_path / "records.db"; _db(db)
    messages = tmp_path / "messages"; messages.mkdir()
    assert subtract_calendar_month(date(2026, 3, 31)) == date(2026, 2, 28)
    assert determine_window(db, messages) == (date(2026, 4, 15), date(2026, 5, 15))


def test_clear_window_preserves_prewindow_and_manual(tmp_path: Path) -> None:
    db = tmp_path / "records.db"; _db(db)
    with Aggregator(db) as agg:
        agg.conn.execute("BEGIN")
        cleared, seasons = _clear_window(agg, date(2026, 4, 15), date(2026, 5, 15))
        agg.conn.commit()
        assert cleared == [2] and seasons == [2026]
        assert agg.conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
        assert agg.conn.execute("SELECT COUNT(*) FROM milestone_records WHERE is_manual = 1").fetchone()[0] == 1


def test_clear_window_removes_message_auto_records_in_window_regardless_of_is_manual(
    tmp_path: Path,
) -> None:
    """message_auto milestone_records are always stored with is_manual=1

    (MilestoneChecker.record_manual_* hardcodes it -- is_manual distinguishes
    the single-row manual-entry code path from the batch boxscore path, not
    "a human typed this"), so clearing must key off `source`, not
    `is_manual`, or a stale award/transfer/injury record silently survives a
    replay and blocks re-derivation.
    """
    db = tmp_path / "records.db"; _db(db)
    with Aggregator(db) as agg:
        conn = agg.conn
        conn.execute(
            "INSERT INTO milestone_records (player_id,milestone_key,milestone_label,scope,season,game_id,achieved_date,achieved_value,source,is_manual) "
            "VALUES (1,'bat_season_award_mvp','MVP','season',2026,NULL,'2026-05-01',1,'message_auto',1)"
        )
        conn.execute(
            "INSERT INTO milestone_records (player_id,milestone_key,milestone_label,scope,season,game_id,achieved_date,achieved_value,source,is_manual) "
            "VALUES (1,'bat_season_award_mvp','MVP','season',2025,NULL,'2025-05-01',1,'message_auto',1)"
        )
        conn.commit()
        conn.execute("BEGIN")
        _clear_window(agg, date(2026, 4, 15), date(2026, 5, 15))
        conn.commit()
        remaining = {
            row[0]
            for row in conn.execute(
                "SELECT achieved_date FROM milestone_records WHERE source = 'message_auto'"
            )
        }
        assert remaining == {"2025-05-01"}


def test_execute_aborts_without_mutation_when_backup_verification_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.replay_recent_window as replay_module

    db = tmp_path / "records.db"; _db(db)
    messages = tmp_path / "messages"; messages.mkdir()
    before = db.read_bytes()
    monkeypatch.setattr(replay_module, "verify_backup", lambda path: False)

    config = RecentReplayConfig(tmp_path / "settings.json", db, tmp_path, tmp_path / "box", messages, Path("data/milestones.csv"), 2026, [], {}, True, 162, execute=True)
    report = replay_module.run_recent_replay(config)

    assert report["integrity"] == "backup_unverified"
    assert report["backup_path"] is None
    assert any("backup" in error for error in report["errors"])
    assert db.read_bytes() == before


def test_dry_run_does_not_mutate_database(tmp_path: Path) -> None:
    db = tmp_path / "records.db"; _db(db)
    messages = tmp_path / "messages"; messages.mkdir()
    before = db.read_bytes()
    config = RecentReplayConfig(tmp_path / "settings.json", db, tmp_path, tmp_path / "box", messages, Path("data/milestones.csv"), 2026, [], {}, True, 162)
    report = run_recent_replay(config)
    assert report["dry_run"] is True
    assert db.read_bytes() == before


def test_failed_execute_keeps_live_db_and_online_backup(tmp_path: Path) -> None:
    db = tmp_path / "records.db"; _db(db)
    messages = tmp_path / "messages"; messages.mkdir()
    before = db.read_bytes()
    config = RecentReplayConfig(tmp_path / "settings.json", db, tmp_path, tmp_path / "missing-boxscores", messages, Path("data/milestones.csv"), 2026, [], {}, True, 162, execute=True)
    report = run_recent_replay(config)
    assert report["integrity"] == "failed_preserved"
    assert db.read_bytes() == before
    assert Path(report["backup_path"]).is_file()


def test_clearing_forgets_only_window_message_and_boxscore_ledgers(tmp_path: Path) -> None:
    db = tmp_path / "records.db"; _db(db)
    messages = tmp_path / "news" / "html" / "messages"; messages.mkdir(parents=True)
    (messages / "message7.txt").write_text("ignored", encoding="utf-8")
    (messages / "messages.dat").write_text('{"message7": "2026-05-15"}', encoding="utf-8")
    source = tmp_path / "game_2.html"; source.write_text("x", encoding="utf-8")
    with Aggregator(db) as agg:
        conn = agg.conn
        conn.execute("INSERT INTO processed_boxscores (filename,game_id,mtime,is_mlb) VALUES ('game_2.html',2,0,0)")
        conn.execute("CREATE TABLE IF NOT EXISTS processed_messages (source_id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO processed_messages (source_id) VALUES ('message7')")
        conn.commit(); conn.execute("BEGIN")
        assert _clear_window_source_state(conn, [source], messages, date(2026, 4, 15), date(2026, 5, 15)) == ["message7"]
        assert conn.execute("SELECT COUNT(*) FROM processed_boxscores WHERE filename='game_2.html'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM processed_messages WHERE source_id='message7'").fetchone()[0] == 0
        conn.commit()


def test_default_message_directory_is_production_news_html_messages(tmp_path: Path) -> None:
    db = tmp_path / "records.db"; _db(db)
    save = tmp_path / "league.lg"; save.mkdir()
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    args = Namespace(settings=str(settings_path), db=str(db), save_path=str(save), boxscore_dir=None, messages_dir=None, milestones="data/milestones.csv", season=2026, execute=False)
    assert _config_from_args(args).messages_dir == save / "news" / "html" / "messages"


def test_config_from_args_rejects_missing_db_settings_or_save_path(tmp_path: Path) -> None:
    db = tmp_path / "records.db"; _db(db)
    save = tmp_path / "league.lg"; save.mkdir()
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    base = dict(settings=str(settings_path), db=str(db), save_path=str(save), boxscore_dir=None, messages_dir=None, milestones="data/milestones.csv", season=2026, execute=False)

    with pytest.raises(ReplayPathError, match="Database not found"):
        _config_from_args(Namespace(**{**base, "db": str(tmp_path / "missing.db")}))
    with pytest.raises(ReplayPathError, match="Save path not found"):
        _config_from_args(Namespace(**{**base, "save_path": str(tmp_path / "missing-save")}))
    with pytest.raises(ReplayPathError, match="Settings file not found"):
        _config_from_args(Namespace(**{**base, "settings": str(tmp_path / "missing-settings.json")}))


def test_config_from_args_never_mutates_via_settings_load(tmp_path: Path) -> None:
    """Loading settings must not create/migrate a records.db as a side effect.

    A real settings.json normally carries a non-empty active_save_path, and
    SettingsManager.load() -> ensure_derived_paths() -> migrate_legacy_shared_db()
    would create a *different* per-save records.db under the app's user-data
    directory purely from being loaded -- independent of --db and before
    --execute. _config_from_args must read settings as plain data instead.
    """
    db = tmp_path / "records.db"; _db(db)
    save = tmp_path / "league.lg"; save.mkdir()
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"active_save_path": str(save), "tracked_teams": ["SY"]}),
        encoding="utf-8",
    )
    user_data_dir = tmp_path / "user_data"
    monkeypatch_paths = pytest.MonkeyPatch()
    try:
        monkeypatch_paths.setattr(
            "core.config.paths.get_user_data_dir", lambda: user_data_dir
        )
        args = Namespace(settings=str(settings_path), db=str(db), save_path=str(save), boxscore_dir=None, messages_dir=None, milestones="data/milestones.csv", season=2026, execute=False)
        config = _config_from_args(args)
        assert config.tracked_teams == ["SY"]
        assert not user_data_dir.exists()
    finally:
        monkeypatch_paths.undo()


def test_message_directory_routing_falls_back_to_save_messages_and_prioritizes_html(tmp_path: Path) -> None:
    save = tmp_path / "league.lg"
    fallback = save / "messages"; fallback.mkdir(parents=True)
    (fallback / "message10058.txt").write_text("x", encoding="utf-8")
    assert _default_messages_dir(save) == fallback
    preferred = save / "news" / "html" / "messages"; preferred.mkdir(parents=True)
    (preferred / "message1.txt").write_text("x", encoding="utf-8")
    assert _default_messages_dir(save) == preferred


def test_custom_alias_mvp_and_cy_fixtures_are_recorded(tmp_path: Path) -> None:
    messages = tmp_path / "news" / "html" / "messages"; messages.mkdir(parents=True)
    fixtures = Path(__file__).parent / "fixtures" / "messages"
    (messages / "message10062.txt").write_text((fixtures / "award_mvp_03.txt").read_text(encoding="utf-8"), encoding="utf-8")
    (messages / "message10058.txt").write_text((fixtures / "award_cy_young_03.txt").read_text(encoding="utf-8"), encoding="utf-8")
    (messages / "messages.dat").write_text('{"message10062":"2027-12-01","message10058":"2027-12-02"}', encoding="utf-8")
    db = tmp_path / "records.db"
    config = RecentReplayConfig(tmp_path / "settings.json", db, tmp_path, tmp_path / "box", messages, Path("data/milestones.csv"), 2027, ["SY"], {"SY": "Seoul Yukies"}, True, 162, execute=True)
    with Aggregator(db) as aggregator:
        checker = MilestoneChecker(aggregator, load_milestones(config.milestones_path), tracked_teams=config.tracked_teams, custom_teams=config.custom_teams, season_games_total=162)
        evidence = _apply_ready_messages(checker, config, date(2027, 11, 2), date(2027, 12, 2))
        assert evidence["expected"] == {"mvp": 1, "cy_young": 1}
        assert evidence["created"] == {"mvp": 1, "cy_young": 1}
        assert evidence["errors"] == []
        keys = {row[0] for row in aggregator.conn.execute("SELECT milestone_key FROM milestone_records WHERE source = 'message_auto'")}
        assert {"bat_season_award_mvp", "pit_season_award_cy_young"} <= keys


def test_replace_retry_handles_transient_windows_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "finalized.db"; source.write_bytes(b"new")
    destination = tmp_path / "live.db"; destination.write_bytes(b"old")
    original_replace = replay.os.replace
    attempts = 0

    def flaky_replace(src: Path, dest: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError(32, "sharing violation")
        original_replace(src, dest)

    monkeypatch.setattr(replay.os, "replace", flaky_replace)
    _replace_with_retry(source, destination, timeout_s=1)
    assert attempts == 3
    assert destination.read_bytes() == b"new"


def test_replace_retry_permanent_failure_preserves_live_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "finalized.db"; source.write_bytes(b"new")
    destination = tmp_path / "live.db"; destination.write_bytes(b"old")
    monkeypatch.setattr(replay.os, "replace", lambda *_: (_ for _ in ()).throw(PermissionError(32, "sharing violation")))
    with pytest.raises(RuntimeError, match="Timed out replacing"):
        _replace_with_retry(source, destination, timeout_s=0)
    assert source.read_bytes() == b"new"
    assert destination.read_bytes() == b"old"


def test_execute_path_can_finalize_and_swap_a_real_sqlite_copy(tmp_path: Path) -> None:
    db = tmp_path / "records.db"; _db(db)
    box = tmp_path / "box"; box.mkdir()
    messages = tmp_path / "messages"; messages.mkdir()
    config = RecentReplayConfig(tmp_path / "settings.json", db, tmp_path, box, messages, Path("data/milestones.csv"), 2026, [], {}, True, 162, execute=True)
    report = run_recent_replay(config)
    assert report["errors"] == []
    assert report["integrity"] == "ok"
    assert Path(report["backup_path"]).is_file()
