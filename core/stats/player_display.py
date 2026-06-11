"""Player name formatting for UI display."""

from __future__ import annotations

import re

_ABBREV_RE = re.compile(r"^[A-Z]\.\s+\S", re.UNICODE)


def looks_abbreviated(name: str) -> bool:
    text = name.strip()
    if not text:
        return False
    if _ABBREV_RE.match(text):
        return True
    return len(text.split()) == 2 and len(text.split()[0]) <= 2 and "." in text.split()[0]


def best_display_name(full_name: str | None, short_name: str | None) -> str:
    """Prefer a non-abbreviated full name when available."""
    full = str(full_name or "").strip()
    short = str(short_name or "").strip()
    if full and not looks_abbreviated(full):
        return full
    if short and not looks_abbreviated(short):
        return short
    if len(full) >= len(short):
        return full or short
    return short or full


def format_player_list_label(player: dict) -> str:
    """List row label with role tags; include ID when name is ambiguous."""
    full = str(player.get("full_name") or "").strip()
    short = str(player.get("short_name") or "").strip()
    display = best_display_name(full, short)
    icons: list[str] = []
    if player.get("is_batter"):
        icons.append("B")
    if player.get("is_pitcher"):
        icons.append("P")
    prefix = f"[{'/'.join(icons)}] " if icons else ""
    player_id = int(player["player_id"])
    if looks_abbreviated(display) or (full and short and full != short and looks_abbreviated(full)):
        return f"{prefix}{display} (#{player_id})"
    return f"{prefix}{display}"


def format_player_header(player: dict) -> str:
    """Multi-line header above stat tables."""
    full = str(player.get("full_name") or "").strip()
    short = str(player.get("short_name") or "").strip()
    display = best_display_name(full, short)
    player_id = int(player["player_id"])
    roles: list[str] = []
    if player.get("is_batter"):
        roles.append("타격")
    if player.get("is_pitcher"):
        roles.append("투구")
    role_text = " · ".join(roles) if roles else "기록 없음"
    lines = [f"<b>{display}</b>", f"ID {player_id} · {role_text}"]
    if full and short and full != short:
        lines.append(f"박스스코어 표기: {short}")
    return "<br>".join(lines)
