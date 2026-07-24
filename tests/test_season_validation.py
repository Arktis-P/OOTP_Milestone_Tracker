"""Validation-only full-season replay tests."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from core.db.schema import init_database
from core.parser.boxscore_html import BoxscoreHTMLParser
from core.stats.aggregator import Aggregator
from core.validation.season_replay import (
    ReplayConfig,
    build_config_from_settings,
    load_message_date_map,
    run_season_replay,
    validation_db_path,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_BOX = ROOT / "samples" / "boxscore_html"
MESSAGE_FIXTURES = ROOT / "tests" / "fixtures" / "messages"
MILESTONES = ROOT / "data" / "milestones.csv"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_save(tmp_path: Path) -> Path:
    save = tmp_path / "SuperYukies Test.lg"
    boxscores = save / "news" / "html" / "box_scores"
    messages = save / "messages"
    boxscores.mkdir(parents=True, exist_ok=True)
    messages.mkdir(parents=True, exist_ok=True)
    (boxscores / "game_box_13.html").write_bytes(
        (SAMPLES_BOX / "game_box_13.html").read_bytes()
    )
    for index, fixture in enumerate(
        ("award_mvp_02.txt", "injury_game_01.txt", "retirement_01.txt"),
        start=1,
    ):
        (messages / f"message{index}.txt").write_text(
            (MESSAGE_FIXTURES / fixture).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return save


def _replace_boxscore_date(path: Path, old: str = "03/27/2026", new: str = "03/27/2025") -> None:
    path.write_text(
        path.read_text(encoding="utf-8").replace(old, new),
        encoding="utf-8",
    )


def _assert_message_partition(report: dict) -> None:
    messages = report["messages"]
    assert messages["total_scanned"] == (
        messages["imported_messages"]
        + messages["skipped"]
        + messages["skipped_outside_season"]
        + len(messages["errors"])
    )


def _config(
    tmp_path: Path,
    *,
    reset: bool = False,
    message_dates: dict[str, date] | None = None,
    live_db: Path | None = None,
) -> ReplayConfig:
    save = _make_save(tmp_path)
    target = validation_db_path(save, 2026, validation_root=tmp_path / "data" / "validation")
    return ReplayConfig(
        save_path=save,
        season=2026,
        tracked_teams=["Seoul Yukies", "Seoul", "SY"],
        mlb_only=True,
        target_db=target,
        live_db=live_db or tmp_path / "data" / "saves" / "live" / "records.db",
        boxscore_dir=save / "news" / "html" / "box_scores",
        messages_dir=save / "messages",
        milestones_path=MILESTONES,
        message_dates=message_dates or {},
        reset=reset,
    )


def test_validation_db_path_is_stable_and_under_validation(tmp_path: Path) -> None:
    save = tmp_path / "Save One.lg"
    first = validation_db_path(save, 2026, validation_root=tmp_path / "data" / "validation")
    second = validation_db_path(save, 2026, validation_root=tmp_path / "data" / "validation")

    assert first == second
    assert first.name == "records.db"
    assert first.parent.name == "season-2026"
    assert first.is_relative_to(tmp_path / "data" / "validation")


def test_replay_imports_boxscores_messages_exclusions_and_missing_dates(
    tmp_path: Path,
) -> None:
    report = run_season_replay(
        _config(tmp_path, reset=True, message_dates={"message1": date(2026, 11, 15)})
    ).to_dict()

    assert report["boxscores"]["total_scanned"] == 1
    assert report["boxscores"]["imported"] == 1
    assert report["messages"]["total_scanned"] == 3
    assert report["messages"]["records_created"] == 1
    assert report["messages"]["imported_messages"] == 1
    assert report["messages"]["skipped"] == 2
    assert report["messages"]["skipped_outside_season"] == 0
    _assert_message_partition(report)
    assert report["messages"]["categories"]["award_mvp"] == 1
    assert report["messages"]["exclusion_reasons"]["message_date_required"] == 1
    assert report["messages"]["exclusion_reasons"]["retirement_milestone_undefined"] == 1
    assert report["messages"]["missing_date_sources"] == ["message2.txt"]
    assert report["db_summary"]["games"] == 1
    assert report["db_summary"]["milestone_records"] == 1

    saved_report = json.loads(Path(report["report_path"]).read_text(encoding="utf-8"))
    assert saved_report["target_db"] == report["target_db"]
    assert saved_report["messages"]["missing_date_count"] == 1


def test_replay_records_boxscore_derived_milestones(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save = _make_save(tmp_path)
    boxscores = save / "news" / "html" / "box_scores"
    (boxscores / "game_box_20.html").write_bytes(
        (SAMPLES_BOX / "game_box_20.html").read_bytes()
    )
    (boxscores / "game_box_13.html").unlink()
    original_parse = BoxscoreHTMLParser.parse

    def parse_with_normalized_notes(parser: BoxscoreHTMLParser):
        data = original_parse(parser)
        if parser.filepath.name == "game_box_20.html":
            data.home_batting_notes = re.sub(
                r"K\. Tucker\s*\n\s*\(2, 5th Inning off R\. Nelson, 0 on, 0 outs\)",
                "K. Tucker 2 (5, 5th Inning off R. Nelson, 0 on, 0 outs)",
                data.home_batting_notes,
            )
        return data

    monkeypatch.setattr(BoxscoreHTMLParser, "parse", parse_with_normalized_notes)
    target = validation_db_path(save, 2026, validation_root=tmp_path / "data" / "validation")

    report = run_season_replay(
        ReplayConfig(
            save_path=save,
            season=2026,
            tracked_teams=[],
            mlb_only=True,
            target_db=target,
            live_db=tmp_path / "live" / "records.db",
            boxscore_dir=boxscores,
            messages_dir=save / "messages",
            milestones_path=MILESTONES,
            reset=True,
        )
    ).to_dict()

    assert report["boxscores"]["achievements_found"] >= 1
    assert report["boxscores"]["achievement_records_created"] >= 1
    assert report["db_summary"]["milestone_records"] >= 1


def test_existing_validation_db_reuses_idempotently_without_reset(tmp_path: Path) -> None:
    config = _config(tmp_path, reset=True, message_dates={"message1": date(2026, 11, 15)})
    first = run_season_replay(config).to_dict()
    second = run_season_replay(
        ReplayConfig(**{**config.__dict__, "reset": False})
    ).to_dict()

    assert first["boxscores"]["imported"] == 1
    assert second["boxscores"]["imported"] == 0
    assert second["boxscores"]["skipped_existing"] == 1
    assert second["messages"]["records_created"] == 0
    _assert_message_partition(second)
    assert second["db_summary"]["milestone_records"] == 1


def test_boxscore_source_filter_selects_only_requested_season(tmp_path: Path) -> None:
    save = _make_save(tmp_path)
    boxscores = save / "news" / "html" / "box_scores"
    outside = boxscores / "game_box_14.html"
    outside.write_bytes((SAMPLES_BOX / "game_box_14.html").read_bytes())
    _replace_boxscore_date(outside, old="03/27/2026", new="03/27/2025")
    invalid = boxscores / "game_box_99.html"
    invalid.write_text(
        "<html><head><title>MLB Box Score, Missing Date</title></head><body></body></html>",
        encoding="utf-8",
    )
    non_mlb = boxscores / "game_box_100.html"
    non_mlb.write_text(
        "<html><head><title>WBC Box Score, Korea at Japan, 03/27/2026</title></head></html>",
        encoding="utf-8",
    )

    report = run_season_replay(
        _config(tmp_path, reset=True, message_dates={"message1": date(2026, 11, 15)})
    ).to_dict()

    assert report["boxscores"]["source_total"] == 4
    assert report["boxscores"]["season_selected"] == 1
    assert report["boxscores"]["skipped_outside_season"] == 1
    assert report["boxscores"]["skipped_non_mlb_source"] == 1
    assert report["boxscores"]["skipped_invalid_date"] == 1
    assert report["boxscores"]["imported_game_ids"] == [13]


def test_reset_recreates_validation_db_only(tmp_path: Path) -> None:
    config = _config(tmp_path, reset=True, message_dates={"message1": date(2026, 11, 15)})
    run_season_replay(config)
    conn = sqlite3.connect(config.target_db)
    try:
        conn.execute(
            """
            INSERT INTO milestone_records (
                player_id, milestone_key, milestone_label, scope, achieved_date, achieved_value
            ) VALUES (999, 'manual_test', 'manual_test', 'manual_event', '2026-01-01', 1)
            """
        )
        conn.commit()
    finally:
        conn.close()

    reset_report = run_season_replay(config).to_dict()

    assert reset_report["db_summary"]["milestone_records"] == 1


def test_path_guard_rejects_live_db_target(tmp_path: Path) -> None:
    save = _make_save(tmp_path)
    live = tmp_path / "data" / "validation" / "live" / "season-2026" / "records.db"
    config = ReplayConfig(
        save_path=save,
        season=2026,
        tracked_teams=[],
        mlb_only=True,
        target_db=live,
        live_db=live,
        boxscore_dir=save / "news" / "html" / "box_scores",
        messages_dir=save / "messages",
        milestones_path=MILESTONES,
        reset=True,
    )

    with pytest.raises(ValueError, match="equals the live DB"):
        run_season_replay(config)


def test_live_db_bytes_unchanged(tmp_path: Path) -> None:
    live_db = tmp_path / "data" / "saves" / "live" / "records.db"
    init_database(live_db)
    before = _hash_file(live_db)

    run_season_replay(
        _config(
            tmp_path,
            reset=True,
            message_dates={"message1": date(2026, 11, 15)},
            live_db=live_db,
        )
    )

    assert _hash_file(live_db) == before


def test_date_map_json_and_csv(tmp_path: Path) -> None:
    json_path = tmp_path / "dates.json"
    json_path.write_text('{"message1": "2026-11-15"}', encoding="utf-8")
    assert load_message_date_map(json_path) == {"message1": date(2026, 11, 15)}

    csv_path = tmp_path / "dates.csv"
    csv_path.write_text("filename,date\nmessage2.txt,2026-05-02\n", encoding="utf-8")
    assert load_message_date_map(csv_path) == {"message2.txt": date(2026, 5, 2)}


def test_messages_outside_requested_season_are_reported_and_not_recorded(tmp_path: Path) -> None:
    save = _make_save(tmp_path)
    (save / "messages" / "message4.txt").write_text(
        (MESSAGE_FIXTURES / "award_mvp_02.txt").read_text(encoding="utf-8").replace("2026", "2025"),
        encoding="utf-8",
    )

    target = validation_db_path(save, 2026, validation_root=tmp_path / "data" / "validation")
    report = run_season_replay(
        ReplayConfig(
            save_path=save,
            season=2026,
            tracked_teams=["Seoul Yukies", "Seoul", "SY"],
            mlb_only=True,
            target_db=target,
            live_db=tmp_path / "live" / "records.db",
            boxscore_dir=save / "news" / "html" / "box_scores",
            messages_dir=save / "messages",
            milestones_path=MILESTONES,
            message_dates={"message1": date(2025, 11, 15)},
            reset=True,
        )
    ).to_dict()

    assert report["messages"]["records_created"] == 0
    assert report["messages"]["skipped"] == 2
    assert report["messages"]["skipped_outside_season"] == 2
    _assert_message_partition(report)
    assert sorted(report["messages"]["outside_season_sources"]) == [
        "message1.txt",
        "message4.txt",
    ]


def test_dry_run_message_partition_is_explicit(tmp_path: Path) -> None:
    report = run_season_replay(
        ReplayConfig(**{**_config(tmp_path).__dict__, "dry_run": True})
    ).to_dict()
    messages = report["messages"]

    assert messages["imported_messages"] == 0
    assert messages["records_created"] == 0
    assert messages["parsed_messages"] == 3
    assert messages["parsed_recordable"] == 1
    assert messages["skipped"] == 2
    assert messages["total_scanned"] == (
        messages["parsed_recordable"]
        + messages["skipped"]
        + messages["skipped_outside_season"]
        + len(messages["errors"])
    )


def test_build_config_from_settings_is_read_only_and_does_not_create_live_db(tmp_path: Path) -> None:
    save = _make_save(tmp_path)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "current_season": 2026,
                "active_save_path": str(save),
                "db_path": str(tmp_path / "live" / "records.db"),
                "milestones_path": str(MILESTONES),
                "import_state": {"boxscore_dir": "keep", "last_import_at": "keep"},
                "tracked_teams": ["SY"],
                "import_mlb_only": True,
            }
        ),
        encoding="utf-8",
    )
    before = settings_path.read_text(encoding="utf-8")
    live_db = tmp_path / "live" / "records.db"
    assert not live_db.exists()

    config = build_config_from_settings(
        settings_path=settings_path,
        validation_root=tmp_path / "data" / "validation",
    )

    assert config.save_path == save
    assert config.tracked_teams == ["SY"]
    assert settings_path.read_text(encoding="utf-8") == before
    assert not live_db.exists()
    assert not (tmp_path / ".legacy_shared_db_migrated").exists()


def test_build_config_rejects_empty_active_save(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"active_save_path": "", "current_season": 2026}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="active_save_path is empty"):
        build_config_from_settings(settings_path=settings_path)


def test_aggregator_import_all_new_accepts_source_snapshot_filter(tmp_path: Path) -> None:
    boxscores = tmp_path / "box"
    boxscores.mkdir()
    for game_id in (13, 14):
        (boxscores / f"game_box_{game_id}.html").write_bytes(
            (SAMPLES_BOX / f"game_box_{game_id}.html").read_bytes()
        )
    snapshot = [Aggregator._file_snapshot(boxscores / "game_box_13.html")]

    with Aggregator(tmp_path / "records.db") as aggregator:
        result = aggregator.import_all_new(boxscores, season=2026, source_snapshot=snapshot)

        assert result.total_scanned == 1
        assert result.imported_game_ids == [13]
        assert aggregator.game_exists(13)
        assert not aggregator.game_exists(14)


def test_aggregator_import_all_new_empty_source_snapshot_imports_zero(tmp_path: Path) -> None:
    boxscores = tmp_path / "box"
    boxscores.mkdir()
    (boxscores / "game_box_13.html").write_bytes(
        (SAMPLES_BOX / "game_box_13.html").read_bytes()
    )

    with Aggregator(tmp_path / "records.db") as aggregator:
        result = aggregator.import_all_new(boxscores, season=2026, source_snapshot=[])

        assert result.total_scanned == 0
        assert result.imported == 0
        assert result.imported_game_ids == []
        assert not aggregator.game_exists(13)
