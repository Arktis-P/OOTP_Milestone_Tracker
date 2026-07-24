"""Capture UI/UX verification screenshots for the orchestrator directive.

The script prefers the real ``MainWindow`` with a temporary ``AppSettings`` and
SQLite DB.  If a page cannot be reached because the current integration branch
is temporarily inconsistent, the failure is recorded in the verification
document instead of silently passing.
"""

from __future__ import annotations

import os
import argparse
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AFTER_DIR = PROJECT_ROOT / "docs" / "ux" / "screenshots" / "after"
REPORT_PATH = PROJECT_ROOT / "docs" / "ux" / "UI_UX_VERIFICATION.md"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class CaptureResult:
    name: str
    filename: str
    requested_size: str
    image_size: str
    non_empty: bool
    checks: str
    status: str
    note: str = ""


def _output_dir(language: str) -> Path:
    return AFTER_DIR / "en" if language == "en" else AFTER_DIR


def _init_sample_db(db_path: Path) -> None:
    from core.db.schema import init_database

    init_database(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO players (player_id, full_name, short_name, primary_position) VALUES (?, ?, ?, ?)",
            (101, "Alpha Hitter", "A. Hitter", "1B"),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO games (
                game_id, date, season, away_team, home_team, away_score, home_score,
                away_innings, home_innings, away_hits, home_hits, away_errors, home_errors,
                is_mlb, is_postseason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (9001, "2026-07-24", 2026, "New York Mets", "Los Angeles Dodgers", 4, 6, "", "", 8, 9, 0, 1, 1, 0),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO batting_logs (
                game_id, player_id, season, team, date, ab, r, h, rbi, bb, k,
                doubles, triples, home_runs, stolen_bases, position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (9001, 101, 2026, "Los Angeles Dodgers", "2026-07-24", 4, 2, 3, 5, 1, 0, 1, 0, 1, 0, "1B"),
        )
        conn.execute(
            """
            INSERT INTO milestone_records (
                player_id, milestone_key, milestone_label, scope, season, game_id,
                achieved_date, achieved_value, notes, team, source, description,
                games_at_achievement
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                101,
                "game_rbi_5",
                "5 RBI Game",
                "game",
                2026,
                9001,
                "2026-07-24",
                5,
                "source:message-sample",
                "Los Angeles Dodgers",
                "message_auto",
                "Sample message automation milestone for UI verification.",
                101,
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO player_streak_state (
                season, player_id, streak_type, run_index, current_value,
                first_success_game_id, first_success_game_date,
                last_success_game_id, last_success_game_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (2026, 101, "hit", 1, 12, 9001, "2026-07-01", 9001, "2026-07-24"),
        )
        conn.commit()
    finally:
        conn.close()


def _make_settings(tmp_dir: Path, *, language: str):
    from core.config.settings_manager import AppSettings, SettingsManager

    save_root = tmp_dir / "saved_games"
    save_path = save_root / "UX Sample.lg"
    (save_path / "news" / "html" / "box_scores").mkdir(parents=True, exist_ok=True)
    (save_path / "news" / "html" / "messages").mkdir(parents=True, exist_ok=True)
    (save_path / "import_export").mkdir(parents=True, exist_ok=True)

    manager = SettingsManager(tmp_dir / "settings.json")
    settings = AppSettings(
        current_season=2026,
        ootp_save_root=str(save_root),
        active_save="UX Sample",
        active_save_path=str(save_path),
        db_path="ux_capture_records.db",
        milestones_path="milestones.csv",
        import_state={"last_import_at": "2026-07-24T09:00:00"},
        initial_stats_dir=str(save_path / "import_export"),
        tracked_teams=["LAD"],
        season_games_total=162,
        language=language,
        language_selected=True,
    )
    settings.paths = {
        "boxscore_dir": str(save_path / "news" / "html" / "box_scores"),
        "game_logs_dir": str(save_path / "news" / "html" / "game_logs"),
        "import_export_dir": str(save_path / "import_export"),
    }
    settings = manager.ensure_derived_paths(settings)
    _init_sample_db(PROJECT_ROOT / "data" / settings.db_path)
    return settings, manager


def _render_widget(app, widget, filename: str, size: tuple[int, int], *, output_dir: Path) -> tuple[str, bool]:
    from PyQt6.QtCore import QSize

    output_dir.mkdir(parents=True, exist_ok=True)
    widget.setMinimumSize(0, 0)
    widget.setMaximumSize(16777215, 16777215)
    widget.resize(QSize(*size))
    widget.setFixedSize(QSize(*size))
    widget.show()
    app.processEvents()
    pixmap = widget.grab()
    app.processEvents()
    path = output_dir / filename
    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"Could not save screenshot: {path}")
    image_size = f"{pixmap.width()}x{pixmap.height()}"
    non_empty = path.stat().st_size > 1024 and pixmap.width() > 0 and pixmap.height() > 0
    widget.hide()
    widget.setMinimumSize(0, 0)
    widget.setMaximumSize(16777215, 16777215)
    app.processEvents()
    return image_size, non_empty


def _capture(
    results: list[CaptureResult],
    app,
    name: str,
    filename: str,
    size: tuple[int, int],
    checks: str,
    build: Callable[[], object],
    *,
    language: str,
) -> None:
    try:
        widget = build()
        image_size, non_empty = _render_widget(
            app, widget, filename, size, output_dir=_output_dir(language)
        )
        status = "captured" if non_empty else "empty-or-invalid"
        display_file = f"en/{filename}" if language == "en" else filename
        results.append(CaptureResult(name, display_file, f"{size[0]}x{size[1]}", image_size, non_empty, checks, status))
        widget.deleteLater()
    except Exception as exc:
        display_file = f"en/{filename}" if language == "en" else filename
        results.append(CaptureResult(name, display_file, f"{size[0]}x{size[1]}", "-", False, checks, "failed", str(exc)))


def _sample_message_item():
    from core.milestone.manual_entry import ManualMilestoneFormData
    from core.milestone.message_automation.parser import ParsedMessage
    from gui.widgets.message_review_model import MessageReviewItem

    parsed = ParsedMessage(
        category="award_mvp",
        title="Alpha Hitter wins MVP",
        excluded=False,
        exclusion_reason=None,
        forms=[
            ManualMilestoneFormData(
                target="player",
                achieved_date=date(2026, 12, 31),
                player_id=101,
                team=None,
                milestone_key="award_mvp",
                season=2026,
                achieved_value=1,
                games_at_achievement=None,
                opponent_team="",
                opponent_player="",
                description="Alpha Hitter wins MVP.",
                notes="source:message-sample",
            )
        ],
        source_id="message-sample",
        player_names={101: "Alpha Hitter"},
    )
    return MessageReviewItem(parsed, raw_text="Alpha Hitter wins MVP\nSample original message body.")


def _write_report(results: list[CaptureResult], mainwindow_note: str) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# UI/UX Verification Evidence",
        "",
        f"- Date: 2026-07-24",
        f"- Mode: QT_QPA_PLATFORM={os.environ.get('QT_QPA_PLATFORM', '')}",
        f"- MainWindow path: {mainwindow_note}",
        "",
        "| Screen | File | Requested size | Image size | Non-empty | Checks | Status | Note |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
    for result in results:
        lines.append(
            "| {name} | {file} | {requested} | {actual} | {non_empty} | {checks} | {status} | {note} |".format(
                name=result.name,
                file=result.filename,
                requested=result.requested_size,
                actual=result.image_size,
                non_empty="yes" if result.non_empty else "no",
                checks=result.checks.replace("|", "/"),
                status=result.status,
                note=result.note.replace("|", "/").replace("\n", " "),
            )
        )
    lines.extend(
        [
            "",
            "## Verification notes",
            "",
            "- The script validates each PNG by checking the captured pixmap dimensions and saved file size.",
            "- Korean captures in `docs/ux/screenshots/after/` are layout, clipping, and control-availability evidence. In the offscreen environment, Korean glyphs may render as tofu boxes because the required font is unavailable; this is an environment limitation, not a UI text-source change.",
            "- Translation completeness is covered by the automated localization tests; the screenshot pass does not replace those tests.",
            "- English captures in `docs/ux/screenshots/after/en/` provide the same layout evidence. This runner reports an empty Qt font database, so glyph readability in both languages still requires a normal Windows desktop check.",
            "- Screens marked `failed` indicate the current branch could not instantiate that view in the offscreen environment; the exception is preserved in the table.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _capture_mainwindow_set(app, tmp_dir: Path, *, language: str, full_set: bool) -> tuple[list[CaptureResult], str]:
    from core.i18n import set_language

    set_language(language)
    settings, manager = _make_settings(tmp_dir, language=language)
    results: list[CaptureResult] = []
    mainwindow_note = f"MainWindow instantiated ({language})"

    try:
        from gui.app import MainWindow

        window = MainWindow(settings=settings, settings_manager=manager)
    except Exception as exc:
        window = None
        mainwindow_note = f"MainWindow failed ({language}): {exc}"

    if window is not None:
        page_map = [
            ("dashboard", "dashboard.png", 0, (1650, 900), "dashboard workflow panel and next actions"),
            ("milestone_basic", "milestone_basic.png", 1, (1650, 900), "basic filters, readable record table"),
            ("import_center", "import_center.png", 5, (1650, 900), "three import cards and five-step flow"),
            ("manual_record_basic", "manual_record_basic.png", 6, (1650, 900), "manual one-record default entry page"),
            ("streak_page", "streak_page.png", 4, (1650, 900), "active/recent streak page with filters"),
            ("settings", "settings.png", 8, (1650, 900), "normal settings separated from advanced tools"),
            ("advanced_tools", "advanced_tools.png", 9, (1650, 900), "maintenance and danger zone separation"),
            ("milestone_1366x768", "milestone_1366x768.png", 1, (1366, 768), "milestone page at 1366x768"),
            ("minimum_1000x680", "minimum_1000x680.png", 1, (1000, 680), "minimum window accessibility"),
        ]
        if not full_set:
            page_map = [
                ("dashboard_en", "dashboard.png", 0, (1650, 900), "English dashboard layout and clipping"),
                ("milestone_1366x768_en", "milestone_1366x768.png", 1, (1366, 768), "English milestone page at 1366x768"),
                ("import_center_en", "import_center.png", 5, (1650, 900), "English import center layout and clipping"),
            ]
        for name, filename, page, size, checks in page_map:
            def build(page=page, name=name):
                window._sidebar.set_current_index(page)
                window._stack.setCurrentIndex(page)
                if name in ("milestone_basic", "milestone_1366x768_en") and window._milestone_view is not None:
                    window._milestone_view.table_panel.table.selectRow(0)
                return window

            _capture(results, app, name, filename, size, checks, build, language=language)

        if full_set:
            def milestone_advanced():
                window._sidebar.set_current_index(1)
                window._stack.setCurrentIndex(1)
                if window._milestone_view is not None:
                    window._milestone_view.advanced_filter_toggle.setChecked(True)
                    window._milestone_view.table_panel.table.selectRow(0)
                return window

            _capture(results, app, "milestone_advanced_filter", "milestone_advanced_filter.png", (1650, 900), "advanced filters expanded", milestone_advanced, language=language)

            def milestone_detail():
                window._sidebar.set_current_index(1)
                window._stack.setCurrentIndex(1)
                if window._milestone_view is not None:
                    window._milestone_view.table_panel.table.selectRow(0)
                return window

            _capture(results, app, "milestone_detail", "milestone_detail.png", (1650, 900), "selected record detail panel", milestone_detail, language=language)
        window.close()
        window.deleteLater()
    return results, mainwindow_note


def _capture_message_review(app, *, language: str, full_set: bool) -> list[CaptureResult]:
    from core.i18n import set_language
    from gui.views.message_review_view import MessageReviewView

    set_language(language)
    results: list[CaptureResult] = []

    def message_review():
        view = MessageReviewView([_sample_message_item()])
        view.table.selectRow(0)
        return view

    name = "message_review" if full_set else "message_review_en"
    checks = (
        "parsed message list, original text, extracted result, approval actions"
        if full_set
        else "English message review layout and clipping"
    )
    _capture(results, app, name, "message_review.png", (1650, 900), checks, message_review, language=language)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--language",
        choices=("ko", "en", "both"),
        default="both",
        help="Capture Korean and/or English layout evidence.",
    )
    args = parser.parse_args()

    from PyQt6.QtWidgets import QApplication
    from gui.theme import apply_app_theme

    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    results: list[CaptureResult] = []
    notes: list[str] = []

    with tempfile.TemporaryDirectory(prefix="ootp-uiux-capture-") as raw_tmp:
        tmp_dir = Path(raw_tmp)
        if args.language in ("ko", "both"):
            ko_results, ko_note = _capture_mainwindow_set(app, tmp_dir / "ko", language="ko", full_set=True)
            results.extend(ko_results)
            results.extend(_capture_message_review(app, language="ko", full_set=True))
            notes.append(ko_note)
        if args.language in ("en", "both"):
            en_results, en_note = _capture_mainwindow_set(app, tmp_dir / "en", language="en", full_set=False)
            results.extend(en_results)
            results.extend(_capture_message_review(app, language="en", full_set=False))
            notes.append(en_note)

    _write_report(results, "; ".join(notes))
    failed = [result for result in results if result.status == "failed"]
    print(f"wrote {REPORT_PATH}")
    print(f"captured {sum(1 for result in results if result.non_empty)} / {len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
