"""Shared combo-box builders for manual milestone/award/transfer/injury entry.

Used by both the inline table rows in ManualMilestoneDialog and the
"enter one at a time" popup dialogs, so player/team lists and autocomplete
behavior stay identical everywhere.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QCompleter

from core.config import AppSettings
from core.i18n import tr
from core.milestone.manual_entry import parse_player_name_list
from core.roster.korean_names import (
    korean_display_for_player,
    load_korean_name_mapper,
    load_roster_player_names,
)
from core.roster.player_registry import PlayerRegistry
from core.stats.aggregator import Aggregator
from core.stats.player_display import format_manual_entry_label, format_player_list_label
from core.stats.team_filter import CANONICAL_MLB_TEAMS, expand_tracked_teams, merge_team_maps

CANONICAL_ROLE = Qt.ItemDataRole.UserRole + 1


def apply_completer(combo: QComboBox) -> None:
    """Attach a case-insensitive substring-match completer to an editable combo."""
    completer = QCompleter(combo.model(), combo)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    combo.setCompleter(completer)


def mlb_team_names(settings: AppSettings) -> list[str]:
    team_map = merge_team_maps(CANONICAL_MLB_TEAMS, settings.custom_mlb_teams)
    return sorted(set(team_map.values()), key=str.lower)


def tracked_team_names(settings: AppSettings) -> list[str]:
    name_map = merge_team_maps(CANONICAL_MLB_TEAMS, settings.custom_mlb_teams)
    names: set[str] = set()
    for token in settings.tracked_teams:
        raw = token.strip()
        if not raw:
            continue
        upper = raw.upper()
        if upper in name_map:
            names.add(name_map[upper])
        elif raw in name_map.values():
            names.add(raw)
        else:
            names.add(raw)
    if not names:
        names.update(expand_tracked_teams(settings.tracked_teams, settings.custom_mlb_teams))
    return sorted(names, key=str.lower)


def fill_player_combo(combo: QComboBox, aggregator: Aggregator, settings: AppSettings) -> None:
    current = combo.currentText()
    combo.blockSignals(True)
    combo.clear()
    seen_ids: set[int] = set()
    mapper = load_korean_name_mapper()
    roster_names = load_roster_player_names(
        settings.import_export_dir or settings.initial_stats_dir or None
    )
    players = aggregator.get_tracked_players(
        settings.tracked_teams, custom_teams=settings.custom_mlb_teams
    )
    for player in players:
        player_id = int(player["player_id"])
        seen_ids.add(player_id)
        base_label = format_player_list_label(player)
        korean = korean_display_for_player(
            mapper,
            full_name=str(player.get("full_name") or ""),
            player_id=player_id,
            roster_names=roster_names,
        )
        label = f"{base_label} / {korean}" if korean else base_label
        combo.addItem(label, player_id)
        combo.setItemData(combo.count() - 1, base_label, CANONICAL_ROLE)
    for player in PlayerRegistry(aggregator).list_manual_players():
        player_id = int(player["player_id"])
        if player_id in seen_ids:
            continue
        player["is_manual"] = True
        combo.addItem(format_manual_entry_label(player), player_id)
    combo.blockSignals(False)
    if current:
        combo.setEditText(current)
    if combo.isEditable():
        apply_completer(combo)


def configure_player_combo(combo: QComboBox, aggregator: Aggregator, settings: AppSettings) -> None:
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    fill_player_combo(combo, aggregator, settings)


def fill_mlb_team_combo(
    combo: QComboBox,
    settings: AppSettings,
    *,
    tracked_first: bool = False,
    blank_first: bool = True,
) -> None:
    combo.clear()
    if blank_first:
        combo.addItem("", "")
    if tracked_first:
        tracked = tracked_team_names(settings)
        tracked_set = set(tracked)
        for name in tracked:
            combo.addItem(name, name)
        for name in mlb_team_names(settings):
            if name not in tracked_set:
                combo.addItem(name, name)
    else:
        for name in mlb_team_names(settings):
            combo.addItem(name, name)


def configure_mlb_team_combo(
    combo: QComboBox, settings: AppSettings, *, tracked_first: bool = False, blank_first: bool = True
) -> None:
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    fill_mlb_team_combo(combo, settings, tracked_first=tracked_first, blank_first=blank_first)
    apply_completer(combo)


def fill_tracked_team_combo(combo: QComboBox, settings: AppSettings) -> None:
    combo.clear()
    for name in tracked_team_names(settings):
        combo.addItem(name, name)


def configure_tracked_team_combo(combo: QComboBox, settings: AppSettings) -> None:
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    fill_tracked_team_combo(combo, settings)
    apply_completer(combo)


def canonical_player_text(combo: QComboBox) -> str:
    """Return canonical player name (without Korean suffix) from a player combo."""
    text = combo.currentText().strip()
    for i in range(combo.count()):
        if combo.itemText(i).strip() == text:
            canonical = combo.itemData(i, CANONICAL_ROLE)
            if canonical is not None:
                return str(canonical)
            break
    return text


def resolve_player_id_from_combo(combo: QComboBox, aggregator: Aggregator) -> int | None:
    text = combo.currentText().strip()
    if not text:
        return None
    for index in range(combo.count()):
        if combo.itemText(index).strip() == text:
            data = combo.itemData(index)
            if data is not None:
                return int(data)
    return PlayerRegistry(aggregator).resolve_player(text)


def ensure_player_id_from_combo(combo: QComboBox, aggregator: Aggregator) -> int | None:
    player_id = resolve_player_id_from_combo(combo, aggregator)
    if player_id is not None:
        return player_id
    text = combo.currentText().strip()
    if not text:
        return None
    try:
        return PlayerRegistry(aggregator).ensure_player(text)
    except ValueError:
        return None


def configure_player_multipick_combo(
    combo: QComboBox,
    aggregator: Aggregator,
    settings: AppSettings,
    on_change: Callable[[], None] | None = None,
) -> None:
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    fill_player_combo(combo, aggregator, settings)
    line = combo.lineEdit()
    if line is not None:
        line.setPlaceholderText(tr("e.g., Dong-ju Moon, A. Judge (comma-separated)"))
    snapshot = {"text": ""}
    original_show_popup = combo.showPopup

    def show_popup() -> None:
        snapshot["text"] = combo.currentText()
        original_show_popup()

    combo.showPopup = show_popup  # type: ignore[method-assign]

    def on_activated(index: int) -> None:
        if index < 0:
            return
        canonical = combo.itemData(index, CANONICAL_ROLE)
        canonical_text = str(canonical) if canonical is not None else combo.itemText(index)
        picked_parts = parse_player_name_list(canonical_text)
        if not picked_parts:
            return
        picked = picked_parts[0]
        parts = parse_player_name_list(snapshot["text"])
        if picked not in parts:
            parts.append(picked)
        text = ", ".join(parts)
        if line is not None:
            line.setText(text)
        snapshot["text"] = text
        if on_change:
            on_change()

    combo.activated.connect(on_activated)
