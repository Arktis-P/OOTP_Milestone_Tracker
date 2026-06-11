"""MLB team registry and abbreviation resolution for tracked-team filters."""

from __future__ import annotations

from typing import Any

# Canonical MLB 30 (one abbreviation per franchise).
CANONICAL_MLB_TEAMS: dict[str, str] = {
    "ARI": "Arizona Diamondbacks",
    "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",
    "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies",
    "CWS": "Chicago White Sox",
    "DET": "Detroit Tigers",
    "HOU": "Houston Astros",
    "KC": "Kansas City Royals",
    "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins",
    "NYM": "New York Mets",
    "NYY": "New York Yankees",
    "OAK": "Oakland Athletics",
    "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates",
    "SD": "San Diego Padres",
    "SEA": "Seattle Mariners",
    "SF": "San Francisco Giants",
    "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",
    "WSH": "Washington Nationals",
}

# Legacy / alternate abbreviations seen in exports or box scores.
MLB_TEAM_ALIASES: dict[str, str] = {
    "ATH": "Oakland Athletics",
    "KCR": "Kansas City Royals",
    "SDP": "San Diego Padres",
    "SFG": "San Francisco Giants",
    "TBR": "Tampa Bay Rays",
    "WSN": "Washington Nationals",
}

MLB_ABBR_TO_NAME: dict[str, str] = {
    **CANONICAL_MLB_TEAMS,
    **MLB_TEAM_ALIASES,
}

_NAME_TO_ABBR = {name.lower(): abbr for abbr, name in CANONICAL_MLB_TEAMS.items()}


def merge_team_maps(*maps: dict[str, str]) -> dict[str, str]:
    """Merge team maps with uppercase abbreviation keys."""
    merged: dict[str, str] = {}
    for team_map in maps:
        for abbr, name in team_map.items():
            key = str(abbr).strip().upper()
            if key and name:
                merged[key] = str(name).strip()
    return merged


def expand_tracked_teams(
    tokens: list[str],
    extra_teams: dict[str, str] | None = None,
) -> list[str]:
    """Return abbreviations and full team names for SQL matching."""
    name_map = merge_team_maps(CANONICAL_MLB_TEAMS, MLB_TEAM_ALIASES, extra_teams or {})
    expanded: set[str] = set()
    for raw in tokens:
        token = raw.strip()
        if not token:
            continue
        expanded.add(token)
        upper = token.upper()
        if upper in name_map:
            expanded.add(name_map[upper])
            expanded.add(upper)
        lowered = token.lower()
        if lowered in _NAME_TO_ABBR:
            canonical = _NAME_TO_ABBR[lowered]
            expanded.add(canonical)
            expanded.add(name_map[canonical])
    return sorted(expanded)


def discover_mlb_teams_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Collect MLB team abbreviations and names from OOTP export rows."""
    teams: dict[str, str] = {}
    for row in rows:
        if int(row.get("league_level_id") or 0) != 1:
            continue
        abbr = str(row.get("team_abbr") or "").strip().upper()
        name = str(row.get("team_name") or "").strip()
        if not abbr:
            continue
        if name or abbr not in teams:
            teams[abbr] = name or teams.get(abbr, abbr)
    return teams


def find_unknown_mlb_teams(
    discovered: dict[str, str],
    known: dict[str, str],
) -> dict[str, str]:
    """Return export teams not present in the known team map."""
    known_keys = {str(key).upper() for key in known}
    unknown: dict[str, str] = {}
    for abbr, name in discovered.items():
        key = abbr.upper()
        if key not in known_keys:
            unknown[key] = name
    return unknown


def sorted_team_items(team_map: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(team_map.items(), key=lambda item: item[1].lower())
