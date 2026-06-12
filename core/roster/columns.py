"""OOTP roster export column indices (OOTP 26 MLB/KBO export, verified 2026-06)."""

from __future__ import annotations

from dataclasses import dataclass

# Canonical header from OOTP export (157 named columns).
# Verified against samples/roster/mlb_rosters.txt & kbo_rosters.txt (2026-06).
# Note: older forum samples (t=354185) had 156 cols without trailing Velo Pot.
CANONICAL_COLUMN_COUNT = 157

# Logical name -> (csv_header, index). Duplicate headers use (name, occurrence).
@dataclass(frozen=True)
class Col:
    header: str
    index: int
    occurrence: int = 0
    note: str = ""


# Aliases: UI/logical label -> actual CSV header (OOTP export typos).
FIELD_ALIASES: dict[str, str] = {
    "Contact vR": "Contract Vr",
    "Gap vR": "Gap Vr",
}

# --- Group 1: basic info (read-only in editor) ---
COL_ID = Col("id", 0)
COL_TEAM_NAME = Col("Team Name", 3)
COL_LEAGUE_NAME = Col("League Name", 4)
COL_LAST_NAME = Col("LastName", 5)
COL_FIRST_NAME = Col("FirstName", 6)
COL_NICK_NAME = Col("NickName", 7)
COL_UNIFORM = Col("UniformNumber", 8)
COL_DAY_OB = Col("DayOB", 9)
COL_MONTH_OB = Col("MonthOB", 10)
COL_YEAR_OB = Col("YearOB", 11)
COL_NATION = Col("Nation", 13)
COL_HEIGHT = Col("Height (cm)", 17)
COL_WEIGHT = Col("Weight (kg)", 18)
COL_BATS = Col("Bats", 19)
COL_THROWS = Col("Throws", 20)
COL_POSITION = Col("Position", 21)

# --- Group 2: batter current ---
BATTER_CURRENT_FIELDS: tuple[Col, ...] = (
    Col("Contact vL", 26),
    Col("Gap vL", 27),
    Col("Power vL", 28),
    Col("Eye vL", 29),
    Col("Avoid K vL", 30),
    Col("BABIP vL", 31),
    Col("Contract Vr", 32, note="OOTP export typo for Contact vR"),
    Col("Gap Vr", 33, note="OOTP export typo for Gap vR"),
    Col("Power vR", 34),
    Col("Eye vR", 35),
    Col("Ks vR", 36, note="vR avoid-K equivalent; no separate Avoid K vR column"),
    Col("BABIP vR", 37),
)

# --- Group 3: batter potential ---
BATTER_POTENTIAL_FIELDS: tuple[Col, ...] = (
    Col("Contact Pot", 38),
    Col("Gap Pot", 39),
    Col("Power Pot", 40),
    Col("Eye Pot", 41),
    Col("Ks Pot", 42),
    Col("BABIP Pot", 43),
)

# --- Group 4: batter misc ---
COL_HBP_BATTER = Col("HBP", 44, occurrence=0)
BATTER_MISC_FIELDS: tuple[Col, ...] = (
    COL_HBP_BATTER,
    Col("GB Batter type", 45),
    Col("FB Batter type", 46),
)

# --- Group 5: running ---
RUNNING_FIELDS: tuple[Col, ...] = (
    Col("speed", 47),
    Col("steal rate", 48),
    Col("steal", 49),
    Col("running", 50),
    Col("sac bunt", 51),
    Col("bunt hit", 52),
)

# --- Group 6: defense ---
DEFENSE_FIELDS: tuple[Col, ...] = (
    Col("Infield Range", 67),
    Col("Infield Error", 68),
    Col("Infield Arm", 69),
    Col("DP", 70),
    Col("CatcherAbil", 71),
    Col("Catcher Arm", 72),
    Col("OF Range", 73),
    Col("OF Error", 74),
    Col("OF Arm", 75),
    Col("Catcher Framing", 155),
)

# --- Group 7: pitcher basic ---
COL_ARMSLOT = Col("ArmSlot", 66)

# --- Group 8: pitcher current ---
PITCHER_CURRENT_FIELDS: tuple[Col, ...] = (
    Col("Move vL", 53),
    Col("Control vL", 54),
    Col("Movement vR", 55),
    Col("Control vR", 56),
    Col("Stuff Overall", 122),
    Col("Velocity", 65),
)

# --- Group 9: pitcher potential ---
# OOTP 26 export has no separate "Velo Pot" column — Velocity at 65 is current only.
PITCHER_POTENTIAL_FIELDS: tuple[Col, ...] = (
    Col("Move Pot", 57),
    Col("Control Pot", 58),
    Col("Stuff Pot.", 124),
    Col("Velo Pot", 156),
)

# --- Group 10: pitch types current (0-5) ---
PITCH_TYPE_CURRENT_FIELDS: tuple[Col, ...] = (
    Col("Fastball (scale: 0-5)", 125),
    Col("Slider", 126),
    Col("Curveball", 127),
    Col("Changeup", 128),
    Col("Cutter", 129),
    Col("Sinker", 130),
    Col("Splitter", 131),
    Col("Forkball", 132),
    Col("Screwball", 133),
    Col("Circlechange", 134),
    Col("Knucklecurve", 135),
    Col("Knuckleball", 136),
)

# --- Group 11: pitch types potential ---
PITCH_TYPE_POTENTIAL_FIELDS: tuple[Col, ...] = (
    Col("Fastball Pot.(scale: 0-5)", 137),
    Col("Slider Pot.", 138),
    Col("Curveball Pot.", 139),
    Col("Changeup Pot.", 140),
    Col("Cutter Pot.", 141),
    Col("Sinker Pot.", 142),
    Col("Splitter Pot.", 143),
    Col("Forkball Pot.", 144),
    Col("Screwball Pot.", 145),
    Col("Circlechange Pot.", 146),
    Col("Knucklecurve Pot.", 147),
    Col("Knuckleball Pot.", 148),
)

# --- Group 12: pitcher misc ---
PITCHER_MISC_FIELDS: tuple[Col, ...] = (
    Col("HBP", 59, occurrence=1),
    Col("WP", 60),
    Col("Balk", 61),
    Col("Stamina", 62),
    Col("Hold", 63),
    Col("GB%", 64),
)

FREE_AGENT_TEAM_NAMES: frozenset[str] = frozenset(
    {"", "Free Agents", "free agents", "FA", "0"}
)


def resolve_header(logical_name: str) -> str:
    return FIELD_ALIASES.get(logical_name, logical_name)


def build_index_map(fieldnames: list[str]) -> dict[tuple[str, int], int]:
    """Map (header, occurrence) -> column index from a loaded roster header."""
    result: dict[tuple[str, int], int] = {}
    counts: dict[str, int] = {}
    for index, name in enumerate(fieldnames):
        occ = counts.get(name, 0)
        result[(name, occ)] = index
        counts[name] = occ + 1
    return result


def validate_fieldnames(fieldnames: list[str]) -> list[str]:
    """Return list of warnings if header diverges from canonical OOTP 26 export."""
    warnings: list[str] = []
    if len(fieldnames) != CANONICAL_COLUMN_COUNT:
        warnings.append(
            f"column count {len(fieldnames)} != canonical {CANONICAL_COLUMN_COUNT}"
        )
    index_map = build_index_map(fieldnames)
    all_cols = (
        BATTER_CURRENT_FIELDS
        + BATTER_POTENTIAL_FIELDS
        + BATTER_MISC_FIELDS
        + RUNNING_FIELDS
        + DEFENSE_FIELDS
        + PITCHER_CURRENT_FIELDS
        + PITCHER_POTENTIAL_FIELDS
        + PITCH_TYPE_CURRENT_FIELDS
        + PITCH_TYPE_POTENTIAL_FIELDS
        + PITCHER_MISC_FIELDS
        + (COL_ARMSLOT, COL_POSITION, COL_TEAM_NAME)
    )
    for col in all_cols:
        key = (col.header, col.occurrence)
        if key not in index_map:
            warnings.append(f"missing column {col.header!r} (occurrence {col.occurrence})")
        elif index_map[key] != col.index:
            warnings.append(
                f"{col.header!r} at index {index_map[key]}, expected {col.index}"
            )
    return warnings
