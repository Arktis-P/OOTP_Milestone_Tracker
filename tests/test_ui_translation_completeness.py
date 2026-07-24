from __future__ import annotations

import ast
from pathlib import Path

from core.i18n.translator import _TRANSLATIONS, set_language, tr


REQUIRED_KOREAN_TRANSLATIONS = (
    "Active Streaks",
    "Recent Events",
    "Next Milestones",
    "All Event Types",
    "Automatic",
    "Official Milestone",
    "Reset Filters",
    "Close",
    "Cancel",
    "Baseline",
    "Analyzing",
    "Saving",
    "keep this window open",
    "common",
    "uncommon",
    "rare",
    "epic",
    "legendary",
)

PHASE_UI_TRANSLATIONS = (
    "Import Workflow Status",
    "Record Import Center",
    "Latest game import",
    "News message import",
    "Career and historical season import",
    "Workflow",
    "Check source files",
    "Analyze and classify",
    "Review differences or extracted records",
    "Save approved changes",
    "Confirm result and unresolved items",
    "Record import completed.",
    "Record import partially completed. Some items need review.",
    "News Message Review",
    "Approve selected",
    "Candidate",
    "Approved",
    "Applied",
    "Excluded",
    "Date needed",
    "Error",
    "Common",
    "Uncommon",
    "Rare",
    "Epic",
    "Legendary",
    "Near",
    "Monitoring",
    "Prediction Basis",
    "Streak Records",
    "Advanced Tools",
    "Danger zone",
)

FORBIDDEN_KOREAN_MODE_LEAKS = (
    "Active Streaks",
    "Recent Events",
    "Next Milestones",
    "All Event Types",
    "Automatic",
    "Official Milestone",
    "Reset Filters",
    "Close",
    "Cancel",
    "Baseline",
    "Analyzing",
    "Saving",
    "keep this window open",
    "Common",
    "Uncommon",
    "Rare",
    "Epic",
    "Legendary",
    "Near",
    "Monitoring",
)

SCANNED_UI_FILES = (
    "gui/app.py",
    "gui/sidebar_nav.py",
    "gui/views/dashboard_view.py",
    "gui/views/milestone_view.py",
    "gui/views/predict_view.py",
    "gui/views/stats_view.py",
    "gui/views/streak_view.py",
    "gui/views/import_center_view.py",
    "gui/views/message_review_view.py",
    "gui/views/advanced_tools_view.py",
    "gui/widgets/import_workflow_status.py",
    "gui/widgets/guided_milestone_form.py",
    "gui/widgets/message_review_model.py",
    "gui/widgets/manual_milestone_dialog.py",
)


def test_required_ui_strings_have_korean_translations() -> None:
    ko = _TRANSLATIONS["ko"]

    required = REQUIRED_KOREAN_TRANSLATIONS + PHASE_UI_TRANSLATIONS
    missing = [key for key in required if key not in ko]
    untranslated = [key for key in required if ko.get(key) == key]

    assert missing == []
    assert untranslated == []


def test_korean_mode_translates_directive_english_strings() -> None:
    set_language("ko")
    try:
        for key in REQUIRED_KOREAN_TRANSLATIONS + PHASE_UI_TRANSLATIONS:
            assert tr(key) != key
    finally:
        set_language("ko")


def test_english_mode_keeps_source_strings() -> None:
    set_language("en")
    try:
        assert tr("Automatic") == "Automatic"
        assert tr("legendary") == "legendary"
        assert tr("Record Import Center") == "Record Import Center"
        assert tr("Prediction Basis") == "Prediction Basis"
    finally:
        set_language("ko")


def _literal_tr_strings(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    strings: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "tr":
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            strings.add(arg.value)
    return strings


def test_scanned_ui_files_cover_forbidden_directive_terms() -> None:
    root = Path(__file__).resolve().parent.parent
    discovered: set[str] = set()
    for relative in SCANNED_UI_FILES:
        path = root / relative
        if path.exists():
            discovered.update(_literal_tr_strings(path))

    ko = _TRANSLATIONS["ko"]
    leaks = [
        key
        for key in FORBIDDEN_KOREAN_MODE_LEAKS
        if key in discovered and ko.get(key, key) == key
    ]
    assert leaks == []


def test_major_new_ui_literals_have_korean_dictionary_entries() -> None:
    root = Path(__file__).resolve().parent.parent
    discovered: set[str] = set()
    for relative in SCANNED_UI_FILES:
        path = root / relative
        if path.exists():
            discovered.update(_literal_tr_strings(path))

    ko = _TRANSLATIONS["ko"]
    required_if_present = [key for key in PHASE_UI_TRANSLATIONS if key in discovered]
    missing = [key for key in required_if_present if key not in ko]
    untranslated = [key for key in required_if_present if ko.get(key) == key]

    assert missing == []
    assert untranslated == []
