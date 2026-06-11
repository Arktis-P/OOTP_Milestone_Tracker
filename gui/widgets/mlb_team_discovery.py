"""Prompt user to register new MLB teams found in OOTP exports."""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox, QWidget

from core.config import AppSettings
from core.stats.initial_import import InitialImporter
from core.stats.team_filter import sorted_team_items


def prompt_unknown_mlb_teams(
    parent: QWidget,
    importer: InitialImporter,
    settings: AppSettings,
    *,
    batting_path: str | None,
    pitching_path: str | None,
) -> AppSettings:
    """Ask to add newly discovered MLB teams to custom_mlb_teams."""
    unknown = importer.discover_unknown_mlb_teams(
        batting_path,
        pitching_path,
        settings.team_name_map(),
    )
    if not unknown:
        return settings

    lines = "\n".join(
        f"  • {abbr} — {name}" for abbr, name in sorted_team_items(unknown)
    )
    reply = QMessageBox.question(
        parent,
        "새 MLB 팀 발견",
        "player stats export에서 기존 MLB 30개 팀에 없는 "
        "신규 MLB 구단(확장 팀 등)이 발견되었습니다.\n\n"
        f"{lines}\n\n"
        "추적 팀 선택 목록에 추가할까요?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return settings

    updated = dict(settings.custom_mlb_teams)
    updated.update(unknown)
    settings.custom_mlb_teams = updated
    return settings
