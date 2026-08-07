"""Tests for `core.milestone.message_automation.discovery`.

Covers messageN.txt filename discovery, verified OOTP 27 binary and defensive
JSON/CSV `messages.dat` parsing, orphan detection, and rescan-status
classification/filtering.
"""

from __future__ import annotations

import json
import struct
from datetime import date
from pathlib import Path

import pytest

from core.milestone.message_automation import discovery
from core.milestone.message_automation.processed import (
    MessageSourceFingerprint,
    upsert_processed_message,
)
from core.stats.aggregator import Aggregator


# ---------------------------------------------------------------------------
# Filename discovery: exact regex, deterministic ordering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "matches"),
    [
        ("message1.txt", True),
        ("message12345.txt", True),
        ("MESSAGE7.TXT", True),
        ("messages.txt", False),
        ("message.txt", False),
        ("message1a.txt", False),
        ("old_message1.txt", False),
        ("message1.txt.bak", False),
        ("message1.dat", False),
    ],
)
def test_message_filename_regex_is_exact(filename: str, matches: bool) -> None:
    assert bool(discovery.MESSAGE_FILENAME_RE.match(filename)) is matches


def test_discover_message_txt_files_orders_numerically_not_lexically(tmp_path: Path) -> None:
    for name in ("message10.txt", "message2.txt", "message1.txt", "messages.txt", "not_a_message.txt"):
        (tmp_path / name).write_text("body", encoding="utf-8")

    found = discovery.discover_message_txt_files(tmp_path)

    assert [path.name for path in found] == ["message1.txt", "message2.txt", "message10.txt"]


def test_discover_message_txt_files_missing_directory_returns_empty(tmp_path: Path) -> None:
    assert discovery.discover_message_txt_files(tmp_path / "does_not_exist") == []


# ---------------------------------------------------------------------------
# messages.dat parsing: JSON/CSV sniffed by content, not extension
# ---------------------------------------------------------------------------


def test_parse_messages_dat_missing_file_degrades_to_missing(tmp_path: Path) -> None:
    result = discovery.parse_messages_dat(tmp_path / "messages.dat")

    assert result.format == "missing"
    assert result.entries == {}
    assert result.warnings == []


def test_parse_messages_dat_sniffs_json_content_despite_dat_extension(tmp_path: Path) -> None:
    dat_path = tmp_path / "messages.dat"
    dat_path.write_text(
        json.dumps({"message1": "2026-04-01", "message2": {"date": "2026-04-15", "id": 2}}),
        encoding="utf-8",
    )

    result = discovery.parse_messages_dat(dat_path)

    assert result.format == "json"
    assert result.entries["message1"].message_date == date(2026, 4, 1)
    assert result.entries["message2"].message_date == date(2026, 4, 15)
    assert result.entries["message2"].message_id == 2
    assert result.warnings == []


def test_parse_messages_dat_sniffs_csv_content_despite_dat_extension(tmp_path: Path) -> None:
    dat_path = tmp_path / "messages.dat"
    dat_path.write_text(
        "source_id,date\nmessage1,2026-04-01\nmessage2,2026-04-15\n",
        encoding="utf-8",
    )

    result = discovery.parse_messages_dat(dat_path)

    assert result.format == "csv"
    assert result.entries["message1"].message_date == date(2026, 4, 1)
    assert result.entries["message2"].message_date == date(2026, 4, 15)


def test_parse_messages_dat_unsupported_binary_degrades_without_raising(tmp_path: Path) -> None:
    dat_path = tmp_path / "messages.dat"
    dat_path.write_bytes(bytes(range(256)))

    result = discovery.parse_messages_dat(dat_path)

    assert result.format == "unsupported"
    assert result.entries == {}
    assert result.warnings


def _ootp27_binary(records: dict[int, date], *, corrupt_slots: set[int] | None = None) -> bytes:
    record_size = 115
    table_offset = 58
    highest = max(records, default=0)
    raw = bytearray(table_offset + (highest + 1) * record_size)
    raw[:6] = b"\x00OOTP\x1b"
    corrupt_slots = corrupt_slots or set()
    for slot in range(highest + 1):
        offset = table_offset + slot * record_size
        struct.pack_into("<I", raw, offset, slot + 5000 if slot in corrupt_slots else slot)
        if slot in records:
            value = records[slot]
            raw[offset + 96] = value.day
            raw[offset + 97] = value.month
            struct.pack_into("<H", raw, offset + 98, value.year)
    return bytes(raw)


def test_parse_messages_dat_ootp27_binary_maps_verified_id_and_date(tmp_path: Path) -> None:
    dat_path = tmp_path / "messages.dat"
    dat_path.write_bytes(
        _ootp27_binary({1: date(2026, 3, 1), 2: date(2026, 3, 2)})
    )

    result = discovery.parse_messages_dat(dat_path)

    assert result.format == "ootp27_binary"
    assert result.entries["message1"].message_id == 1
    assert result.entries["message1"].message_date == date(2026, 3, 1)
    assert result.entries["message2"].message_date == date(2026, 3, 2)


def test_parse_messages_dat_ootp27_binary_skips_one_corrupt_record(tmp_path: Path) -> None:
    dat_path = tmp_path / "messages.dat"
    dat_path.write_bytes(
        _ootp27_binary(
            {1: date(2026, 3, 1), 2: date(2026, 3, 2), 3: date(2026, 3, 3)},
            corrupt_slots={2},
        )
    )

    result = discovery.parse_messages_dat(dat_path)

    assert "message1" in result.entries
    assert "message2" not in result.entries
    assert result.entries["message3"].message_date == date(2026, 3, 3)
    assert result.warnings


def test_parse_messages_dat_unknown_ootp_binary_version_is_unsupported(tmp_path: Path) -> None:
    dat_path = tmp_path / "messages.dat"
    raw = bytearray(_ootp27_binary({1: date(2026, 3, 1)}))
    raw[5] = 26
    dat_path.write_bytes(raw)

    result = discovery.parse_messages_dat(dat_path)

    assert result.format == "unsupported"
    assert result.entries == {}


def test_parse_messages_dat_json_skips_bad_entries_without_failing_the_rest(tmp_path: Path) -> None:
    dat_path = tmp_path / "messages.dat"
    dat_path.write_text(
        json.dumps({"message1": "2026-04-01", "message2": 12345, "message3": "not-a-date"}),
        encoding="utf-8",
    )

    result = discovery.parse_messages_dat(dat_path)

    assert result.format == "json"
    assert result.entries["message1"].message_date == date(2026, 4, 1)
    assert "message2" not in result.entries
    assert result.entries["message3"].message_date is None
    assert result.warnings  # message2 (int value) reported, not silently dropped


# ---------------------------------------------------------------------------
# discover_messages: correlation, orphan metadata vs orphan txt
# ---------------------------------------------------------------------------


def test_discover_messages_correlates_dates_and_flags_orphans(tmp_path: Path) -> None:
    messages_dir = tmp_path / "messages"
    messages_dir.mkdir()
    (messages_dir / "message1.txt").write_text("body one", encoding="utf-8")
    (messages_dir / "message2.txt").write_text("body two", encoding="utf-8")
    dat_path = messages_dir / "messages.dat"
    dat_path.write_text(
        json.dumps({"message1": "2026-04-01", "message999": "2026-04-20"}),
        encoding="utf-8",
    )

    scan = discovery.discover_messages(messages_dir)

    by_id = {m.source_id: m for m in scan.messages}
    assert by_id["message1"].message_date == date(2026, 4, 1)
    assert by_id["message1"].metadata_matched is True
    # message2.txt is an orphan txt file: no matching metadata entry.
    assert by_id["message2"].message_date is None
    assert by_id["message2"].metadata_matched is False
    # message999 is orphan metadata: no matching txt file on disk.
    assert scan.orphan_metadata_keys == ["message999"]


def test_discover_messages_without_dat_still_returns_all_txt_files(tmp_path: Path) -> None:
    messages_dir = tmp_path / "messages"
    messages_dir.mkdir()
    (messages_dir / "message1.txt").write_text("body", encoding="utf-8")

    scan = discovery.discover_messages(messages_dir)

    assert scan.metadata.format == "missing"
    assert len(scan.messages) == 1
    assert scan.messages[0].message_date is None
    assert scan.warnings  # missing-metadata warning surfaced, scan not aborted


def test_discover_messages_falls_back_to_parent_directory_for_dat(tmp_path: Path) -> None:
    save_root = tmp_path / "save"
    messages_dir = save_root / "messages"
    messages_dir.mkdir(parents=True)
    (messages_dir / "message1.txt").write_text("body", encoding="utf-8")
    (save_root / "messages.dat").write_text(
        json.dumps({"message1": "2026-05-05"}), encoding="utf-8"
    )

    scan = discovery.discover_messages(messages_dir)

    assert scan.metadata.format == "json"
    assert scan.messages[0].message_date == date(2026, 5, 5)


# ---------------------------------------------------------------------------
# scan_message_directory: classification against processed_messages
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path):
    agg = Aggregator(tmp_path / "discovery.db")
    yield agg.conn
    agg.close()


def test_scan_message_directory_reports_new_for_unseen_files(tmp_path: Path, conn) -> None:
    messages_dir = tmp_path / "messages"
    messages_dir.mkdir()
    (messages_dir / "message1.txt").write_text("body", encoding="utf-8")

    entries = discovery.scan_message_directory(conn, messages_dir)

    assert len(entries) == 1
    assert entries[0].status == discovery.STATUS_NEW


def test_scan_message_directory_reports_already_applied_then_changed(tmp_path: Path, conn) -> None:
    messages_dir = tmp_path / "messages"
    messages_dir.mkdir()
    message_path = messages_dir / "message1.txt"
    message_path.write_text("original body", encoding="utf-8")

    from core.milestone.message_automation.processed import fingerprint_message_file

    upsert_processed_message(
        conn,
        fingerprint=fingerprint_message_file(message_path),
        status="applied",
        created_record_ids=[42],
        mark_applied=True,
    )

    entries = discovery.scan_message_directory(conn, messages_dir)
    assert entries[0].status == discovery.STATUS_ALREADY_APPLIED

    message_path.write_text("edited body", encoding="utf-8")
    entries_after_edit = discovery.scan_message_directory(conn, messages_dir)
    assert entries_after_edit[0].status == discovery.STATUS_CHANGED


def test_scan_message_directory_reports_excluded_and_error_statuses(tmp_path: Path, conn) -> None:
    messages_dir = tmp_path / "messages"
    messages_dir.mkdir()
    excluded_path = messages_dir / "message1.txt"
    excluded_path.write_text("excluded body", encoding="utf-8")
    error_path = messages_dir / "message2.txt"
    error_path.write_text("error body", encoding="utf-8")

    from core.milestone.message_automation.processed import fingerprint_message_file

    upsert_processed_message(
        conn,
        fingerprint=fingerprint_message_file(excluded_path),
        status="excluded",
        exclusion_reason="excluded_by_reviewer",
    )
    upsert_processed_message(
        conn,
        fingerprint=fingerprint_message_file(error_path),
        status="error",
        errors=["boom"],
    )

    entries = discovery.scan_message_directory(conn, messages_dir)
    by_id = {entry.source_id: entry for entry in entries}
    assert by_id["message1"].status == discovery.STATUS_EXCLUDED
    assert by_id["message2"].status == discovery.STATUS_ERROR


def test_scan_message_directory_degrades_one_unreadable_file_without_stopping(
    tmp_path: Path, conn, monkeypatch
) -> None:
    messages_dir = tmp_path / "messages"
    messages_dir.mkdir()
    ok_path = messages_dir / "message1.txt"
    ok_path.write_text("ok body", encoding="utf-8")
    bad_path = messages_dir / "message2.txt"
    bad_path.write_text("bad body", encoding="utf-8")

    real_fingerprint = discovery.fingerprint_message_file

    def flaky_fingerprint(path):
        if Path(path).name == "message2.txt":
            raise OSError("simulated locked file")
        return real_fingerprint(path)

    monkeypatch.setattr(discovery, "fingerprint_message_file", flaky_fingerprint)

    entries = discovery.scan_message_directory(conn, messages_dir)
    by_id = {entry.source_id: entry for entry in entries}

    assert by_id["message1"].status == discovery.STATUS_NEW
    assert by_id["message2"].status == discovery.STATUS_ERROR
    assert len(entries) == 2  # scan continued past the unreadable file


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("new", discovery.STATUS_NEW),
        ("changed_review_needed", discovery.STATUS_CHANGED),
        ("already_applied", discovery.STATUS_ALREADY_APPLIED),
        ("excluded", discovery.STATUS_EXCLUDED),
        ("error", discovery.STATUS_ERROR),
        ("candidate", discovery.STATUS_UNRESOLVED),
        ("duplicate", discovery.STATUS_UNRESOLVED),
        ("skipped", discovery.STATUS_UNRESOLVED),
        ("something_unexpected", discovery.STATUS_UNRESOLVED),
    ],
)
def test_classify_rescan_status_mapping(raw_status: str, expected: str) -> None:
    assert discovery.classify_rescan_status(raw_status) == expected


# ---------------------------------------------------------------------------
# filter_scan_entries: status set + inclusive date range
# ---------------------------------------------------------------------------


def _entry(source_id: str, status: str, message_date: date | None) -> discovery.MessageScanEntry:
    return discovery.MessageScanEntry(
        source_id=source_id,
        message_id=int(source_id.removeprefix("message")),
        path=Path(f"{source_id}.txt"),
        message_date=message_date,
        metadata_matched=message_date is not None,
        fingerprint=MessageSourceFingerprint(
            source_id=source_id, source_path="", source_hash="h", source_mtime=0.0
        ),
        status=status,
    )


def test_filter_scan_entries_by_status() -> None:
    entries = [
        _entry("message1", discovery.STATUS_NEW, date(2026, 4, 1)),
        _entry("message2", discovery.STATUS_ALREADY_APPLIED, date(2026, 4, 2)),
        _entry("message3", discovery.STATUS_ERROR, None),
    ]

    filtered = discovery.filter_scan_entries(entries, statuses={discovery.STATUS_NEW, discovery.STATUS_ERROR})

    assert [entry.source_id for entry in filtered] == ["message1", "message3"]


def test_filter_scan_entries_by_date_range_excludes_unknown_dates() -> None:
    entries = [
        _entry("message1", discovery.STATUS_NEW, date(2026, 4, 1)),
        _entry("message2", discovery.STATUS_NEW, date(2026, 4, 10)),
        _entry("message3", discovery.STATUS_NEW, date(2026, 4, 20)),
        _entry("message4", discovery.STATUS_NEW, None),
    ]

    filtered = discovery.filter_scan_entries(
        entries, date_from=date(2026, 4, 5), date_to=date(2026, 4, 15)
    )

    assert [entry.source_id for entry in filtered] == ["message2"]


def test_filter_scan_entries_date_range_is_inclusive() -> None:
    entries = [
        _entry("message1", discovery.STATUS_NEW, date(2026, 4, 5)),
        _entry("message2", discovery.STATUS_NEW, date(2026, 4, 15)),
    ]

    filtered = discovery.filter_scan_entries(
        entries, date_from=date(2026, 4, 5), date_to=date(2026, 4, 15)
    )

    assert {entry.source_id for entry in filtered} == {"message1", "message2"}
