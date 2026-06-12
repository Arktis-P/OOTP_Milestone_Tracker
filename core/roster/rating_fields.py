"""Field group definitions for the player rating editor dialog."""

from __future__ import annotations

from dataclasses import dataclass

from core.roster.row_access import RowField


@dataclass(frozen=True)
class RatingSection:
    title: str
    fields: tuple[RowField, ...]
    readonly: bool = False


def _f(name: str, *, occurrence: int = 0, label: str | None = None) -> RowField:
    return RowField(name=name, occurrence=occurrence, label=label)


BASIC_INFO_SECTION = RatingSection(
    title="선수 기본 정보",
    readonly=True,
    fields=(
        _f("id"),
        _f("Team Name", label="Team Name"),
        _f("League Name", label="League Name"),
        _f("LastName"),
        _f("FirstName"),
        _f("NickName"),
        _f("UniformNumber"),
        _f("DayOB"),
        _f("MonthOB"),
        _f("YearOB"),
        _f("Nation"),
        _f("Height (cm)"),
        _f("Weight (kg)"),
        _f("Bats"),
        _f("Throws"),
        _f("Position"),
    ),
)

RATING_SECTIONS: tuple[RatingSection, ...] = (
    BASIC_INFO_SECTION,
    RatingSection(
        title="타자 현재 레이팅",
        fields=(
            _f("Contact vL"),
            _f("Gap vL"),
            _f("Power vL"),
            _f("Eye vL"),
            _f("Avoid K vL"),
            _f("BABIP vL"),
            _f("Contract Vr", label="Contact vR"),
            _f("Gap Vr", label="Gap vR"),
            _f("Power vR"),
            _f("Eye vR"),
            _f("Ks vR"),
            _f("BABIP vR"),
        ),
    ),
    RatingSection(
        title="타자 포텐셜",
        fields=(
            _f("Contact Pot"),
            _f("Gap Pot"),
            _f("Power Pot"),
            _f("Eye Pot"),
            _f("Ks Pot"),
            _f("BABIP Pot"),
        ),
    ),
    RatingSection(
        title="타자 기타",
        fields=(
            _f("HBP", occurrence=0, label="HBP"),
            _f("GB Batter type"),
            _f("FB Batter type"),
        ),
    ),
    RatingSection(
        title="주루/작전",
        fields=(
            _f("speed"),
            _f("steal rate"),
            _f("steal"),
            _f("running"),
            _f("sac bunt"),
            _f("bunt hit"),
        ),
    ),
    RatingSection(
        title="수비",
        fields=(
            _f("Infield Range"),
            _f("Infield Error"),
            _f("Infield Arm"),
            _f("DP"),
            _f("CatcherAbil"),
            _f("Catcher Arm"),
            _f("Catcher Framing"),
            _f("OF Range"),
            _f("OF Error"),
            _f("OF Arm"),
        ),
    ),
    RatingSection(
        title="투수 기본",
        fields=(_f("ArmSlot"),),
    ),
    RatingSection(
        title="투수 현재 레이팅",
        fields=(
            _f("Move vL"),
            _f("Control vL"),
            _f("Movement vR"),
            _f("Control vR"),
            _f("Stuff Overall"),
            _f("Velocity"),
        ),
    ),
    RatingSection(
        title="투수 포텐셜",
        fields=(
            _f("Move Pot"),
            _f("Control Pot"),
            _f("Stuff Pot."),
            _f("Velo Pot"),
        ),
    ),
    RatingSection(
        title="투구 종류 현재 레이팅",
        fields=(
            _f("Fastball (scale: 0-5)"),
            _f("Slider"),
            _f("Curveball"),
            _f("Changeup"),
            _f("Cutter"),
            _f("Sinker"),
            _f("Splitter"),
            _f("Forkball"),
            _f("Screwball"),
            _f("Circlechange"),
            _f("Knucklecurve"),
            _f("Knuckleball"),
        ),
    ),
    RatingSection(
        title="투구 종류 포텐셜",
        fields=(
            _f("Fastball Pot.(scale: 0-5)"),
            _f("Slider Pot."),
            _f("Curveball Pot."),
            _f("Changeup Pot."),
            _f("Cutter Pot."),
            _f("Sinker Pot."),
            _f("Splitter Pot."),
            _f("Forkball Pot."),
            _f("Screwball Pot."),
            _f("Circlechange Pot."),
            _f("Knucklecurve Pot."),
            _f("Knuckleball Pot."),
        ),
    ),
    RatingSection(
        title="투수 기타",
        fields=(
            _f("HBP", occurrence=1, label="HBP (투수)"),
            _f("WP"),
            _f("Balk"),
            _f("Stamina"),
            _f("Hold"),
            _f("GB%"),
        ),
    ),
)
