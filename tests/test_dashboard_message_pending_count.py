from __future__ import annotations

from pathlib import Path

from core.milestone.message_automation.processed import (
    fingerprint_message_file,
    upsert_processed_message,
)
from core.stats.aggregator import Aggregator
from gui.views.dashboard_view import _count_message_files


def _message_dir(save: Path) -> Path:
    directory = save / "news" / "html" / "messages"
    directory.mkdir(parents=True)
    return directory


def test_pending_count_excludes_unchanged_applied_duplicate_and_reviewer_excluded(
    tmp_path: Path,
) -> None:
    save = tmp_path / "league.lg"
    directory = _message_dir(save)
    paths = []
    for index in range(1, 8):
        path = directory / f"message{index}.txt"
        path.write_text(f"message {index}", encoding="utf-8")
        paths.append(path)

    aggregator = Aggregator(tmp_path / "records.db")
    try:
        for path, status in zip(
            paths[:5],
            ["applied", "duplicate", "excluded", "applied", "duplicate"],
        ):
            upsert_processed_message(
                aggregator.conn,
                fingerprint=fingerprint_message_file(path),
                status=status,
                exclusion_reason=(
                    "excluded_by_reviewer" if status == "excluded" else None
                ),
                mark_applied=status == "applied",
            )

        assert _count_message_files(str(save), aggregator.conn) == 2
    finally:
        aggregator.close()


def test_changed_applied_source_returns_to_pending(tmp_path: Path) -> None:
    save = tmp_path / "league.lg"
    directory = _message_dir(save)
    path = directory / "message1.txt"
    path.write_text("original", encoding="utf-8")
    aggregator = Aggregator(tmp_path / "records.db")
    try:
        upsert_processed_message(
            aggregator.conn,
            fingerprint=fingerprint_message_file(path),
            status="applied",
            mark_applied=True,
        )
        assert _count_message_files(str(save), aggregator.conn) == 0

        path.write_text("changed", encoding="utf-8")
        assert _count_message_files(str(save), aggregator.conn) == 1
    finally:
        aggregator.close()

