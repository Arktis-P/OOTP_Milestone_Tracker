"""Parse OOTP box score HTML files."""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from core.parser.common import (
    DATE_MDY_RE,
    DECISION_RE,
    HOLD_RE,
    GAME_BOX_ID_RE,
    GAME_ID_RE,
    ParserError,
    SUB_LABEL_RE,
    extract_player_id,
    parse_date_iso,
    parse_float,
    parse_game_id_from_filename,
    parse_int,
    parse_ip,
    parse_team_record,
)
from core.stats.models import (
    BatterLine,
    BoxscoreData,
    GameMeta,
    GameNotes,
    LineScore,
    PitcherLine,
)

BoxScoreHtmlParseError = ParserError

_BOXSCORE_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)


def peek_is_mlb_boxscore(filepath: str | Path, *, read_limit: int = 8192) -> bool:
    """Return True if the file looks like an MLB box score (header peek only)."""
    path = Path(filepath)
    if not path.is_file():
        return False
    head = path.read_text(encoding="utf-8", errors="replace")[:read_limit]
    match = _BOXSCORE_TITLE_RE.search(head)
    if match and match.group(1).strip().startswith("MLB Box Score"):
        return True
    if "MAJOR LEAGUE BASEBALL" in head and "major_league_baseball.png" in head:
        return True
    return False


class BoxscoreHTMLParser:
    def __init__(self, filepath: str | Path) -> None:
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise ParserError(f"File not found: {self.filepath}")
        self._soup: BeautifulSoup | None = None

    def parse(self) -> BoxscoreData:
        html = self.filepath.read_text(encoding="utf-8")
        self._soup = BeautifulSoup(html, "html.parser")
        soup = self._soup

        linescore = self._parse_linescore(soup)
        meta = self._parse_game_meta(soup, linescore)
        away_batting, home_batting = self._parse_batting_tables(soup, linescore)
        away_pitching, home_pitching = self._parse_pitching_tables(soup, linescore)
        away_notes, home_notes = self._parse_batting_notes(soup)
        away_pitch_notes, home_pitch_notes = self._parse_pitching_notes(soup)
        game_notes = self._parse_game_notes(soup)

        return BoxscoreData(
            meta=meta,
            away_batting=away_batting,
            home_batting=home_batting,
            away_pitching=away_pitching,
            home_pitching=home_pitching,
            away_batting_notes=away_notes,
            home_batting_notes=home_notes,
            away_pitching_notes=away_pitch_notes,
            home_pitching_notes=home_pitch_notes,
            game_notes=game_notes,
        )

    def _parse_game_meta(self, soup: BeautifulSoup, linescore: LineScore) -> GameMeta:
        title = soup.title.get_text(strip=True) if soup.title else ""
        date_raw = ""
        title_match = re.search(
            r"Box Score,\s*(.+?)\s+at\s+(.+?),\s*(\d{1,2}/\d{1,2}/\d{4})",
            title,
            re.I,
        )
        if title_match:
            date_raw = title_match.group(3)
        else:
            date_div = soup.find("div", style=re.compile(r"padding-top:4px"))
            if date_div:
                date_raw = date_div.get_text(strip=True)

        if not date_raw:
            raise ParserError("Could not find game date in box score HTML")

        game_id = self._extract_game_id(soup)
        game_notes = self._parse_game_notes(soup)

        return GameMeta(
            game_id=game_id,
            date=parse_date_iso(date_raw),
            away_team=linescore.away_team,
            home_team=linescore.home_team,
            away_score=linescore.away_score,
            home_score=linescore.home_score,
            away_record=linescore.away_record,
            home_record=linescore.home_record,
            away_innings=linescore.away_innings,
            home_innings=linescore.home_innings,
            away_hits=linescore.away_hits,
            home_hits=linescore.home_hits,
            away_errors=linescore.away_errors,
            home_errors=linescore.home_errors,
            ballpark=game_notes.ballpark,
            attendance=game_notes.attendance,
            game_time=game_notes.game_time,
        )

    def _extract_game_id(self, soup: BeautifulSoup) -> int:
        from_file = parse_game_id_from_filename(self.filepath.name, GAME_BOX_ID_RE)
        if from_file is not None:
            return from_file

        for td in soup.find_all("td"):
            text = td.get_text(" ", strip=True)
            match = GAME_ID_RE.search(text)
            if match:
                return int(match.group(1))

        raise ParserError("Could not determine game_id")

    def _parse_linescore(self, soup: BeautifulSoup) -> LineScore:
        for table in soup.find_all("table", class_="data"):
            header_row = table.find("tr")
            if not header_row:
                continue
            headers = [th.get_text(strip=True) for th in header_row.find_all("th")]
            if "R" not in headers or "H" not in headers:
                continue

            data_rows = [
                row
                for row in table.find_all("tr")[1:]
                if row.find("td", class_="dl") and row.find_all("td", class_="dc")
            ]
            if len(data_rows) < 2:
                continue

            away_cells = data_rows[0].find_all("td")
            home_cells = data_rows[1].find_all("td")

            away_team, away_record = parse_team_record(away_cells[0].get_text(" ", strip=True))
            home_team, home_record = parse_team_record(home_cells[0].get_text(" ", strip=True))

            away_inning_cells = away_cells[1:-3]
            home_inning_cells = home_cells[1:-3]

            return LineScore(
                away_team=away_team,
                home_team=home_team,
                away_record=away_record,
                home_record=home_record,
                away_innings=[parse_int(td.get_text()) for td in away_inning_cells],
                home_innings=[parse_int(td.get_text()) for td in home_inning_cells],
                away_score=parse_int(away_cells[-3].get_text()),
                home_score=parse_int(home_cells[-3].get_text()),
                away_hits=parse_int(away_cells[-2].get_text()),
                home_hits=parse_int(home_cells[-2].get_text()),
                away_errors=parse_int(away_cells[-1].get_text()),
                home_errors=parse_int(home_cells[-1].get_text()),
            )

        raise ParserError("Could not find linescore table")

    def _parse_batting_tables(
        self, soup: BeautifulSoup, linescore: LineScore
    ) -> tuple[list[BatterLine], list[BatterLine]]:
        tables = self._find_stat_tables(soup, required_header="AB")
        if len(tables) < 2:
            raise ParserError("Expected two batting linescore tables")
        away = self._parse_batting(soup, tables[0], linescore.away_team)
        home = self._parse_batting(soup, tables[1], linescore.home_team)
        return away, home

    def _parse_pitching_tables(
        self, soup: BeautifulSoup, linescore: LineScore
    ) -> tuple[list[PitcherLine], list[PitcherLine]]:
        tables = self._find_stat_tables(soup, required_header="IP")
        if len(tables) < 2:
            raise ParserError("Expected two pitching linescore tables")
        away = self._parse_pitching(soup, tables[0], linescore.away_team)
        home = self._parse_pitching(soup, tables[1], linescore.home_team)
        return away, home

    def _find_stat_tables(self, soup: BeautifulSoup, required_header: str) -> list[Tag]:
        tables: list[Tag] = []
        for table in soup.find_all("table"):
            classes = table.get("class") or []
            if "sortable" not in classes:
                continue
            headers = [th.get_text(strip=True) for th in table.find_all("th", class_="hsn")]
            if required_header in headers:
                tables.append(table)
        return tables

    def _parse_batting(self, soup: BeautifulSoup, table: Tag, team: str) -> list[BatterLine]:
        rows: list[BatterLine] = []
        for row in table.find_all("tr"):
            if "sortbottom" in (row.get("class") or []):
                continue
            player_td = row.find("td", class_="dl")
            if not player_td:
                continue
            stat_cells = row.find_all("td", class_="dc")
            if len(stat_cells) < 10:
                continue

            batter = self._parse_batter_row(player_td, stat_cells, team)
            if batter:
                rows.append(batter)
        return rows

    def _parse_batter_row(
        self, player_td: Tag, stat_cells: list[Tag], team: str
    ) -> BatterLine | None:
        link = player_td.find("a", href=re.compile(r"player_\d+"))
        if not link:
            return None

        player_name = link.get_text(strip=True)
        player_id = extract_player_id(link.get("href"))
        if player_id is None:
            raise ParserError(f"Missing player_id for batter: {player_name}")

        raw_text = player_td.get_text(" ", strip=True).replace("\xa0", " ").strip()
        is_substitute = bool(re.match(r"^[a-z]-", raw_text, re.I))
        sub_label = ""
        if is_substitute:
            sub_match = SUB_LABEL_RE.match(raw_text)
            sub_label = sub_match.group(1).lower() if sub_match else ""

        position = raw_text.split(player_name, 1)[-1].strip()
        if is_substitute and sub_label:
            position = re.sub(rf"^{sub_label}-\s*", "", position, flags=re.I).strip()

        values = [cell.get_text(strip=True) for cell in stat_cells]
        return BatterLine(
            player_name=player_name,
            player_id=player_id,
            team=team,
            position=position,
            is_substitute=is_substitute,
            sub_label=sub_label,
            ab=parse_int(values[0]),
            r=parse_int(values[1]),
            h=parse_int(values[2]),
            rbi=parse_int(values[3]),
            bb=parse_int(values[4]),
            k=parse_int(values[5]),
            lob=parse_int(values[6]),
            avg=parse_float(values[7]),
            season_hr=parse_int(values[8]),
            season_rbi=parse_int(values[9]),
        )

    def _parse_pitching(self, soup: BeautifulSoup, table: Tag, team: str) -> list[PitcherLine]:
        rows: list[PitcherLine] = []
        for row in table.find_all("tr"):
            player_td = row.find("td", class_="dl")
            if not player_td:
                continue
            stat_cells = row.find_all("td", class_="dc")
            if len(stat_cells) < 10:
                continue

            pitcher = self._parse_pitcher_row(player_td, stat_cells, team)
            if pitcher:
                rows.append(pitcher)
        return rows

    def _parse_pitcher_row(
        self, player_td: Tag, stat_cells: list[Tag], team: str
    ) -> PitcherLine | None:
        link = player_td.find("a", href=re.compile(r"player_\d+"))
        if not link:
            return None

        player_name = link.get_text(strip=True)
        player_id = extract_player_id(link.get("href"))
        if player_id is None:
            raise ParserError(f"Missing player_id for pitcher: {player_name}")

        remainder = player_td.get_text(" ", strip=True).replace(player_name, "", 1).strip()
        decision = ""
        decision_record = ""
        decision_match = DECISION_RE.search(remainder)
        if decision_match:
            decision = decision_match.group(1)
            if decision == "SV":
                decision = "S"
            decision_record = f"({decision_match.group(2)})"

        hold_earned = False
        season_holds = 0
        hold_match = HOLD_RE.search(remainder)
        if hold_match:
            hold_earned = True
            season_holds = int(hold_match.group(1))

        values = [cell.get_text(strip=True) for cell in stat_cells]
        return PitcherLine(
            player_name=player_name,
            player_id=player_id,
            team=team,
            decision=decision,
            decision_record=decision_record,
            hold_earned=hold_earned,
            season_holds=season_holds,
            ip=parse_ip(values[0]),
            h=parse_int(values[1]),
            r=parse_int(values[2]),
            er=parse_int(values[3]),
            bb=parse_int(values[4]),
            k=parse_int(values[5]),
            hr=parse_int(values[6]),
            bf=parse_int(values[7]),
            pi=parse_int(values[8]),
            era=parse_float(values[9]),
        )

    def _parse_batting_notes(self, soup: BeautifulSoup) -> tuple[str, str]:
        batting_tables = self._find_stat_tables(soup, required_header="AB")
        notes: list[str] = []
        for table in batting_tables[:2]:
            databg = table.find_parent("td", class_="databg")
            text = ""
            if databg:
                batting_tag = databg.find("b", string=re.compile(r"BATTING", re.I))
                if batting_tag:
                    text = batting_tag.find_parent("td").get_text("\n", strip=True)
            notes.append(text)
        while len(notes) < 2:
            notes.append("")
        return notes[0], notes[1]

    def _parse_pitching_notes(self, soup: BeautifulSoup) -> tuple[str, str]:
        pitching_tables = self._find_stat_tables(soup, required_header="IP")
        notes: list[str] = []
        for table in pitching_tables[:2]:
            databg = table.find_parent("td", class_="databg")
            text = ""
            if databg:
                pitching_tag = databg.find("b", string=re.compile(r"^PITCHING$", re.I))
                if pitching_tag:
                    text = pitching_tag.find_parent("td").get_text("\n", strip=True)
            notes.append(text)
        while len(notes) < 2:
            notes.append("")
        return notes[0], notes[1]

    def _parse_game_notes(self, soup: BeautifulSoup) -> GameNotes:
        notes = GameNotes()
        header = soup.find("td", class_="boxtitle", string=re.compile(r"GAME NOTES", re.I))
        if not header:
            return notes

        content_td = header.find_parent("tr").find_next_sibling("tr")
        if not content_td:
            return notes
        td = content_td.find("td", class_="databg")
        if not td:
            return notes

        pog = td.find("b", string=re.compile(r"Player of the Game", re.I))
        if pog:
            link = pog.find_parent().find("a", href=re.compile(r"player_\d+"))
            if link:
                notes.player_of_game = link.get_text(strip=True)
                notes.player_of_game_id = extract_player_id(link.get("href"))

        lines = [line.strip() for line in td.get_text("\n", strip=True).split("\n") if line.strip()]
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            inline_value = ""

            if ":" in line:
                label, _, remainder = line.partition(":")
                label = label.strip()
                inline_value = remainder.strip()
            else:
                label = line
                remainder = ""

            def next_value() -> str:
                nonlocal idx
                if inline_value:
                    return inline_value
                if idx + 1 < len(lines) and not lines[idx + 1].endswith(":"):
                    idx += 1
                    return lines[idx]
                return ""

            if label == "Ballpark":
                notes.ballpark = next_value()
            elif label == "Weather":
                notes.weather = next_value()
            elif label == "Start Time":
                notes.start_time = next_value()
            elif label == "Time":
                notes.game_time = next_value()
            elif label == "Attendance":
                notes.attendance = parse_int(next_value())
            elif label == "Special Notes":
                notes.special_notes = self._extract_special_notes(td)
            idx += 1

        return notes

    @staticmethod
    def _extract_special_notes(td: Tag) -> str:
        full = td.get_text(" ", strip=True)
        marker = "Special Notes:"
        if marker not in full:
            return ""
        return full.split(marker, 1)[1].strip()


def parse_boxscore_html(file_path: str | Path) -> BoxscoreData:
    """Parse an OOTP HTML box score file."""
    return BoxscoreHTMLParser(file_path).parse()
