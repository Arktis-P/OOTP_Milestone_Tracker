"""Composite milestone specs (e.g. 20-20)."""

from __future__ import annotations

from dataclasses import dataclass

from core.milestone.definitions import MilestoneDefinition


@dataclass(frozen=True)
class HrSbSpec:
    hr_min: int
    sb_min: int


def parse_hr_sb_spec(spec: str) -> HrSbSpec | None:
    text = spec.strip()
    if "-" not in text:
        return None
    left, right = text.split("-", 1)
    try:
        return HrSbSpec(hr_min=int(left.strip()), sb_min=int(right.strip()))
    except ValueError:
        return None


def hr_sb_met(hr: float, sb: float, spec: HrSbSpec) -> bool:
    return hr >= spec.hr_min and sb >= spec.sb_min


def hr_sb_crossed(
    prior_hr: float,
    current_hr: float,
    prior_sb: float,
    current_sb: float,
    spec: HrSbSpec,
) -> bool:
    was_met = hr_sb_met(prior_hr, prior_sb, spec)
    now_met = hr_sb_met(current_hr, current_sb, spec)
    return not was_met and now_met


def composite_crossed(
    milestone: MilestoneDefinition,
    prior: dict[str, float],
    current: dict[str, float],
) -> bool:
    if milestone.stat != "season_hr_sb":
        return False
    spec = parse_hr_sb_spec(milestone.threshold_spec)
    if spec is None:
        return False
    return hr_sb_crossed(
        prior.get("hr", 0.0),
        current.get("hr", 0.0),
        prior.get("sb", 0.0),
        current.get("sb", 0.0),
        spec,
    )
