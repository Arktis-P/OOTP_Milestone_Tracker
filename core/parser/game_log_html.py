"""Parse OOTP game log HTML files."""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from core.parser.common import (
    GAME_LOG_ID_RE,
    INNING_HEADER_RE,
    INNING_SUMMARY_RE,
    ParserError,
    cell_text_with_lines,
    extract_distance,
    extract_exit_velocity,
    extract_hit_type,
    extract_player_id,
    normalize_result,
    parse_date_iso,
    parse_game_id_from_filename,
    parse_int,
)
from core.stats.models import AtBatData, GameLogData, InningData, InningSummary

# ---------------------------------------------------------------------------
# Base / out state tracking helpers
# ---------------------------------------------------------------------------

_RUNNER_ATTEMPT_RE = re.compile(
    r"Runner from (1st|2nd|3rd) tries for (Home|3rd|2nd|1st), (SAFE|OUT)", re.I
)
_PITCH_LINE_RE = re.compile(r"^\d+-\d+:")
_ACTION_KEYWORDS = (
    "scores", "to second", "to third", "to home",
    "steals 2nd", "steals 3rd", "steals second", "steals third",
    "is caught stealing", "caught stealing",
)
_NON_NAME_PREFIXES = (
    "Runner from", "Passed Ball", "Wild Pitch", "Balk!",
    "Pickoff", "Lined into", "Batter ", "Now in", "Pinch ",
)
_BASE_MAP = {"1st": "1", "2nd": "2", "3rd": "3"}


class _InningState:
    """Tracks base occupancy and out count within a half-inning."""

    def __init__(self) -> None:
        self.outs: int = 0
        self._bases: dict[str, str] = {}  # "1" / "2" / "3" → runner name

    def reset(self) -> None:
        self.outs = 0
        self._bases = {}

    def snapshot(self) -> tuple[bool, bool, bool]:
        return ("1" in self._bases, "2" in self._bases, "3" in self._bases)

    # --- runner helpers ---

    def _base_of(self, name: str) -> str | None:
        for base, runner in self._bases.items():
            if runner == name:
                return base
        return None

    def _move(self, name: str, to_base: str) -> None:
        old = self._base_of(name)
        if old:
            del self._bases[old]
        self._bases[to_base] = name

    def _remove(self, name: str) -> None:
        old = self._base_of(name)
        if old:
            del self._bases[old]

    # --- event application ---

    def apply_runner_event(self, player_name: str, action: str) -> None:
        act = action.lower()
        if "caught stealing" in act:
            self._remove(player_name)
            self.outs += 1
        elif "scores" in act or "to home" in act:
            self._remove(player_name)
        elif "to second" in act or "steals 2nd" in act or "steals second" in act:
            self._move(player_name, "2")
        elif "to third" in act or "steals 3rd" in act or "steals third" in act:
            self._move(player_name, "3")
        elif "to first" in act:
            self._move(player_name, "1")

    def apply_runner_attempt(self, event_line: str) -> None:
        m = _RUNNER_ATTEMPT_RE.search(event_line)
        if not m:
            return
        from_base = _BASE_MAP.get(m.group(1).lower(), "")
        to_place = m.group(2).lower()
        outcome = m.group(3).lower()
        runner_name = self._bases.pop(from_base, "")
        if outcome == "out":
            self.outs += 1
        else:  # safe
            to_base_map = {"home": None, "3rd": "3", "2nd": "2", "1st": "1"}
            to_base = to_base_map.get(to_place)
            if to_base and runner_name:
                self._bases[to_base] = runner_name
        # "trailing runner, OUT!" → one additional out + clear lowest base
        if "trailing runner" in event_line.lower() and "out!" in event_line.lower():
            for b in ("1", "2", "3"):
                if b in self._bases and b != from_base:
                    del self._bases[b]
                    break
            self.outs += 1

    def apply_pinch_runner(self, runner_name: str, base: str) -> None:
        self._bases[base] = runner_name

    def _apply_force(self, batter_name: str) -> None:
        """Force-advance all runners for walk/HBP, then put batter on 1st."""
        if "1" in self._bases:
            if "2" in self._bases:
                if "3" in self._bases:
                    del self._bases["3"]  # forced home, scores
                self._bases["3"] = self._bases["2"]
            self._bases["2"] = self._bases["1"]
        self._bases["1"] = batter_name

    def apply_result(self, result: str, batter_name: str) -> None:
        r = result.lower()
        if r == "single":
            self._bases["1"] = batter_name
        elif r == "double":
            self._bases["2"] = batter_name
        elif r == "triple":
            self._bases["3"] = batter_name
        elif r == "home run":
            self._bases.clear()
        elif r in ("walk", "hit by pitch", "error"):
            self._apply_force(batter_name)
        elif r == "fielders choice":
            for b in ("1", "2", "3"):
                if b in self._bases:
                    del self._bases[b]
                    break
            self._bases["1"] = batter_name
            self.outs += 1
        elif r == "double play" or "lined into" in r:
            if "1" in self._bases:
                del self._bases["1"]
            self.outs += 2
        elif "caught stealing" in r or "is caught stealing" in r:
            pass  # out already counted by runner event
        else:
            self.outs += 1  # strikeout, fly out, ground out, etc.


def _is_non_name_line(line: str) -> bool:
    if _PITCH_LINE_RE.match(line):
        return True
    if line.startswith("("):
        return True
    if line.isupper():
        return True
    return any(line.startswith(p) for p in _NON_NAME_PREFIXES)


def _parse_runner_events(lines: list[str]) -> list[tuple[str, str]]:
    """Return (player_name, action) pairs and ("", special_event_line) entries."""
    events: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if _RUNNER_ATTEMPT_RE.search(line):
            events.append(("", line))
            i += 1
            continue
        if _is_non_name_line(line):
            i += 1
            continue
        # Check if next line is an action
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and any(kw in next_line.lower() for kw in _ACTION_KEYWORDS):
                events.append((line, next_line))
                i += 2
                continue
        i += 1
    return events


def _update_state(state: _InningState, at_bat: AtBatData) -> None:
    """Apply runner events and batter result to advance state."""
    lines = at_bat.pitch_sequence.split("\n")
    events = _parse_runner_events(lines)
    for player_name, action in events:
        if player_name:
            state.apply_runner_event(player_name, action)
        else:
            state.apply_runner_attempt(action)
    state.apply_result(at_bat.result, at_bat.batter_name)


class GameLogHTMLParser:
    def __init__(self, filepath: str | Path) -> None:
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise ParserError(f"File not found: {self.filepath}")
        self._current_pitcher_name = ""
        self._current_pitcher_id: int | None = None

    def parse(self) -> GameLogData:
        html = self.filepath.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")

        game_id = self._extract_game_id(soup)
        away_team, home_team, date_raw = self._parse_header(soup)
        innings = self._parse_innings(soup)

        return GameLogData(
            game_id=game_id,
            date=parse_date_iso(date_raw),
            away_team=away_team,
            home_team=home_team,
            innings=innings,
        )

    def _extract_game_id(self, soup: BeautifulSoup) -> int:
        from_file = parse_game_id_from_filename(self.filepath.name, GAME_LOG_ID_RE)
        if from_file is not None:
            return from_file
        raise ParserError("Could not determine game_id from game log filename")

    def _parse_header(self, soup: BeautifulSoup) -> tuple[str, str, str]:
        title = soup.title.get_text(strip=True) if soup.title else ""
        if "@" in title:
            away_team, home_team = [part.strip() for part in title.split("@", 1)]
        else:
            subtitle = soup.find("div", class_="repsubtitle")
            if subtitle:
                text = subtitle.get_text(strip=True)
                away_team, home_team = self._split_teams_from_header(text)
            else:
                raise ParserError("Could not parse teams from game log header")

        date_div = soup.find("div", style=re.compile(r"padding-top:4px"))
        if not date_div:
            raise ParserError("Could not find game date in game log HTML")
        date_raw = date_div.get_text(strip=True)
        return away_team, home_team, date_raw

    @staticmethod
    def _split_teams_from_header(text: str) -> tuple[str, str]:
        cleaned = text.replace("@", " AT ")
        if " AT " in cleaned:
            away, home = cleaned.split(" AT ", 1)
            return away.strip().title(), home.strip().title()
        raise ParserError(f"Could not split teams from header: {text}")

    def _parse_innings(self, soup: BeautifulSoup) -> list[InningData]:
        innings: list[InningData] = []
        state = _InningState()
        _PINCH_RUNNER_RE = re.compile(r"Pinch Runner at (1st|2nd|3rd)", re.I)

        for table in soup.find_all("table", class_="data"):
            header_th = table.find("th", class_="boxtitle")
            if not header_th:
                continue
            header_text = header_th.get_text(" ", strip=True)
            header_match = INNING_HEADER_RE.search(header_text)
            if not header_match:
                continue

            half = header_match.group(1).upper()
            inning_num = int(header_match.group(2))
            batting_team, pitching_team = self._parse_inning_teams(table)
            state.reset()

            inning = InningData(
                inning_num=inning_num,
                half=half,
                batting_team=batting_team,
                pitching_team=pitching_team,
                at_bats=[],
            )

            for row in table.find_all("tr"):
                summary_td = row.find("td", class_="datathbg")
                if summary_td:
                    inning.summary = self._parse_inning_summary(
                        summary_td.get_text(" ", strip=True),
                        batting_team,
                        pitching_team,
                    )
                    continue

                cells = row.find_all("td", class_="dl")
                if len(cells) < 2:
                    if len(cells) == 1:
                        left_text = cells[0].get_text(" ", strip=True)
                        if left_text.startswith("Pitching:"):
                            self._update_current_pitcher(cells[0])
                    continue

                left_text = cells[0].get_text(" ", strip=True)
                if left_text.startswith("Pitching:"):
                    self._update_current_pitcher(cells[0])
                    continue

                # Pinch runner substitution → update base state
                pr_match = _PINCH_RUNNER_RE.match(left_text)
                if pr_match:
                    base = _BASE_MAP.get(pr_match.group(1).lower(), "")
                    link = cells[0].find("a", href=re.compile(r"player_\d+"))
                    runner_name = link.get_text(strip=True) if link else ""
                    if base and runner_name:
                        state.apply_pinch_runner(runner_name, base)
                    continue

                if left_text.startswith("Batting:"):
                    outs_snap = state.outs
                    runners_snap = state.snapshot()
                    at_bat = self._parse_at_bat(row, inning_num, half)
                    if at_bat:
                        at_bat.outs_before = outs_snap
                        at_bat.runners_before = runners_snap
                        _update_state(state, at_bat)
                        inning.at_bats.append(at_bat)

            innings.append(inning)
        return innings

    def _parse_inning_teams(self, table: Tag) -> tuple[str, str]:
        team_th = table.find(
            "th",
            attrs={"colspan": "2"},
            string=re.compile(r"batting\s*-\s*Pitching for", re.I),
        )
        if not team_th:
            team_th = table.find("th", colspan="2")
        if not team_th:
            return "", ""

        text = team_th.get_text(" ", strip=True)
        match = re.search(
            r"(.+?)\s+batting\s*-\s*Pitching for\s+(.+?)\s*:\s*(?:LHP|RHP)",
            text,
            re.I,
        )
        if not match:
            return "", ""
        return match.group(1).strip(), match.group(2).strip()

    def _update_current_pitcher(self, cell: Tag) -> None:
        link = cell.find("a", href=re.compile(r"player_\d+"))
        if link:
            self._current_pitcher_name = link.get_text(strip=True)
            self._current_pitcher_id = extract_player_id(link.get("href"))
        else:
            text = cell.get_text(" ", strip=True)
            name = re.sub(r"^Pitching:\s*(?:LHP|RHP)\s*", "", text, flags=re.I).strip()
            self._current_pitcher_name = name
            self._current_pitcher_id = None

    def _parse_at_bat(self, row: Tag, inning_num: int, half: str) -> AtBatData | None:
        cells = row.find_all("td", class_="dl")
        if len(cells) < 2:
            return None

        batter_cell = cells[0]
        pitch_cell = cells[1]
        batter_text = batter_cell.get_text(" ", strip=True)
        if not batter_text.startswith("Batting:"):
            return None

        hand_match = re.search(r"Batting:\s*(LHB|RHB|SHB)", batter_text, re.I)
        batter_hand = hand_match.group(1).upper() if hand_match else ""

        link = batter_cell.find("a", href=re.compile(r"player_\d+"))
        if not link:
            return None

        batter_name = link.get_text(strip=True)
        batter_id = extract_player_id(link.get("href"))
        if batter_id is None:
            raise ParserError(f"Missing batter_id for {batter_name}")

        pitch_sequence = cell_text_with_lines(pitch_cell)
        result = self._extract_result(pitch_cell, pitch_sequence)

        return AtBatData(
            inning=inning_num,
            half=half,
            batter_name=batter_name,
            batter_id=batter_id,
            batter_hand=batter_hand,
            pitcher_name=self._current_pitcher_name,
            pitcher_id=self._current_pitcher_id,
            pitch_sequence=pitch_sequence,
            result=result,
            hit_type=extract_hit_type(pitch_sequence),
            exit_velocity=extract_exit_velocity(pitch_sequence),
            distance=extract_distance(pitch_sequence),
        )

    def _extract_result(self, pitch_cell: Tag, pitch_text: str) -> str:
        bolds = pitch_cell.find_all("b")
        for bold in reversed(bolds):
            text = bold.get_text(strip=True)
            if text and not text.startswith("Runner"):
                return normalize_result(text)

        lines = [line.strip() for line in pitch_text.split("\n") if line.strip()]
        if not lines:
            return ""
        last_line = lines[-1]
        last_line = re.sub(r"^\d+-\d+:\s*", "", last_line).strip()
        return normalize_result(last_line)

    def _parse_inning_summary(
        self, text: str, batting_team: str, pitching_team: str
    ) -> InningSummary:
        match = INNING_SUMMARY_RE.search(text)
        if not match:
            return InningSummary(
                runs=0,
                hits=0,
                errors=0,
                lob=0,
                away_score=0,
                home_score=0,
                away_team=batting_team,
                home_team=pitching_team,
            )

        away_team = match.group(5).strip()
        away_score = parse_int(match.group(6))
        home_team = match.group(7).strip()
        home_score = parse_int(match.group(8))

        return InningSummary(
            runs=parse_int(match.group(1)),
            hits=parse_int(match.group(2)),
            errors=parse_int(match.group(3)),
            lob=parse_int(match.group(4)),
            away_score=away_score,
            home_score=home_score,
            away_team=away_team,
            home_team=home_team,
        )


def parse_game_log_html(file_path: str | Path) -> GameLogData:
    """Parse an OOTP HTML game log file."""
    return GameLogHTMLParser(file_path).parse()


def _half_label(half: str) -> str:
    return "초" if half.upper() == "TOP" else "말"


def _format_at_bat_raw(at_bat: AtBatData) -> str:
    hand = at_bat.batter_hand or ""
    batter = at_bat.batter_name
    pitcher = at_bat.pitcher_name or ""
    result = at_bat.result or ""
    sequence = (at_bat.pitch_sequence or "").replace("\n", " ").strip()
    parts = [f"Batting: {hand} {batter}".strip()]
    if pitcher:
        parts.append(f"vs {pitcher}")
    if sequence:
        parts.append(sequence)
    if result:
        parts.append(f"→ {result}")
    return " ".join(parts)


def extract_player_at_bats(log_path: str | Path, player_id: int) -> list[dict]:
    """
    Extract raw at-bat text for a player as batter or pitcher.

    No base-state simulation — returns verbatim log snippets for GUI hints.
    """
    data = GameLogHTMLParser(log_path).parse()
    entries: list[dict] = []
    seen: set[tuple[int, str, str, str]] = set()

    for inning in data.innings:
        for at_bat in inning.at_bats:
            is_batter = at_bat.batter_id == player_id
            is_pitcher = at_bat.pitcher_id == player_id
            if not is_batter and not is_pitcher:
                continue
            raw_text = _format_at_bat_raw(at_bat)
            key = (at_bat.inning, at_bat.half, raw_text, at_bat.result)
            if key in seen:
                continue
            seen.add(key)
            label = f"{at_bat.inning}회{_half_label(at_bat.half)}"
            entries.append(
                {
                    "inning": at_bat.inning,
                    "half": at_bat.half,
                    "label": label,
                    "raw_text": raw_text,
                    "role": "batter" if is_batter else "pitcher",
                }
            )
    return entries
