"""State model for reviewing parsed OOTP news messages before saving.

The message automation parser already returns ``ParsedMessage`` objects.  This
module adds the UI-facing review state around those immutable parser results so
the GUI can preview, approve, exclude, repair missing dates, and only then call
the injected persistence callback.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import date
from typing import Any, Iterable

from core.i18n import tr
from core.milestone.message_automation.parser import ParsedMessage
from core.milestone.manual_entry import (
    ManualInjuryFormData,
    ManualMilestoneFormData,
    ManualTransferFormData,
    validate_manual_injury,
    validate_manual_transfer,
)
from gui.widgets.guided_milestone_form import display_field, editable_field_values


STATUS_CANDIDATE = "candidate"
STATUS_APPROVED = "approved"
STATUS_APPLIED = "applied"
STATUS_EXCLUDED = "excluded"
STATUS_DATE_NEEDED = "date_needed"
STATUS_ERROR = "error"

REVIEW_STATUSES = (
    STATUS_CANDIDATE,
    STATUS_APPROVED,
    STATUS_APPLIED,
    STATUS_EXCLUDED,
    STATUS_DATE_NEEDED,
    STATUS_ERROR,
)


@dataclass
class MessageReviewItem:
    """One parsed message plus review-only state."""

    parsed: ParsedMessage
    raw_text: str = ""
    message_date: date | None = None
    status: str | None = None
    error: str = ""
    notice: str = ""
    created_record_ids: list[int] = field(default_factory=list)
    duplicate_record_ids: list[int] = field(default_factory=list)
    manually_edited: bool = False

    def __post_init__(self) -> None:
        if self.status is None:
            self.status = self._initial_status()
        if self.parsed.source_id is None:
            self.parsed = replace(self.parsed, source_id="")

    @property
    def source_id(self) -> str:
        return str(self.parsed.source_id or "")

    @property
    def title(self) -> str:
        return self.parsed.title

    @property
    def category(self) -> str:
        return self.parsed.category

    @property
    def generated_count(self) -> int:
        return len(self.parsed.forms)

    @property
    def reason(self) -> str:
        if self.error:
            return self.error
        if self.notice:
            return self.notice
        if self.duplicate_record_ids:
            return "duplicate"
        if self.parsed.excluded:
            return self.parsed.exclusion_reason or ""
        if self.status == STATUS_DATE_NEEDED:
            return "Date confirmation required before saving."
        return ""

    def can_approve(self) -> bool:
        return self.status == STATUS_CANDIDATE and self.generated_count > 0

    def can_save(self) -> bool:
        return self.status == STATUS_APPROVED and self.generated_count > 0

    def needs_date(self) -> bool:
        return any(getattr(form, "achieved_date", None) is None for form in self.parsed.forms)

    def _initial_status(self) -> str:
        if self.error:
            return STATUS_ERROR
        if self.created_record_ids:
            return STATUS_APPLIED
        if self.parsed.excluded:
            return STATUS_EXCLUDED
        if self.needs_date():
            return STATUS_DATE_NEEDED
        return STATUS_CANDIDATE if self.parsed.forms else STATUS_EXCLUDED


class MessageReviewModel:
    """Pure-Python state container used by the message review view and tests."""

    def __init__(self, items: Iterable[MessageReviewItem] = ()) -> None:
        self._items = list(items)

    @property
    def items(self) -> list[MessageReviewItem]:
        return self._items

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> MessageReviewItem:
        return self._items[index]

    def set_items(self, items: Iterable[MessageReviewItem]) -> None:
        self._items = list(items)

    def filtered_indexes(self, filter_key: str = "all") -> list[int]:
        if filter_key == "all":
            return list(range(len(self._items)))
        return [
            index
            for index, item in enumerate(self._items)
            if item.status == filter_key
        ]

    def summary_counts(self) -> dict[str, int]:
        """Return the directive-required summary buckets."""

        counts = Counter(item.status for item in self._items)
        return {
            "total": len(self._items),
            "candidates": counts[STATUS_CANDIDATE] + counts[STATUS_APPROVED],
            "approved": counts[STATUS_APPROVED],
            "applied": counts[STATUS_APPLIED],
            "excluded": counts[STATUS_EXCLUDED],
            "date_needed": counts[STATUS_DATE_NEEDED],
            "errors": counts[STATUS_ERROR],
        }

    def approve(self, indexes: Iterable[int]) -> int:
        changed = 0
        for item in self._resolve_indexes(indexes):
            if item.can_approve():
                item.status = STATUS_APPROVED
                changed += 1
        return changed

    def approve_all_candidates(self) -> int:
        return self.approve(range(len(self._items)))

    def exclude(self, indexes: Iterable[int], reason: str = "Excluded by reviewer.") -> int:
        changed = 0
        for item in self._resolve_indexes(indexes):
            if item.status not in (STATUS_APPLIED, STATUS_ERROR):
                item.status = STATUS_EXCLUDED
                item.parsed = replace(item.parsed, excluded=True, exclusion_reason=reason)
                changed += 1
        return changed

    def assign_date(self, indexes: Iterable[int], achieved_date: date) -> int:
        """Apply one date to selected date-missing messages and return updates."""

        changed = 0
        for item in self._resolve_indexes(indexes):
            if item.status != STATUS_DATE_NEEDED:
                continue
            item.parsed = replace(
                item.parsed,
                forms=[_form_with_date(form, achieved_date) for form in item.parsed.forms],
            )
            item.message_date = achieved_date
            item.status = STATUS_CANDIDATE
            changed += 1
        return changed

    def update_parsed(self, index: int, parsed: ParsedMessage, raw_text: str | None = None) -> None:
        item = self._items[index]
        was_applied = item.status == STATUS_APPLIED
        item.parsed = parsed
        if raw_text is not None:
            item.raw_text = raw_text
        item.error = ""
        item.manually_edited = False
        if was_applied:
            item.status = STATUS_APPLIED
        else:
            item.created_record_ids = []
            item.duplicate_record_ids = []
            item.status = item._initial_status()

    def update_form_fields(
        self,
        index: int,
        form_index: int,
        values: dict[str, str],
    ) -> None:
        """Apply user-edited form fields with conversion before approval/save.

        Conversion failures are stored on the row and move it to ``error`` so
        ``approved_items`` cannot return it for persistence.
        """

        item = self._items[index]
        try:
            forms = list(item.parsed.forms)
            if not (0 <= form_index < len(forms)):
                raise ValueError("Selected extracted form is not available.")
            forms[form_index] = update_form_values(forms[form_index], values)
            item.parsed = replace(item.parsed, forms=forms, excluded=False, exclusion_reason=None)
            item.error = ""
            item.created_record_ids = []
            item.manually_edited = True
            item.status = STATUS_CANDIDATE
        except ValueError as exc:
            item.error = str(exc)
            item.status = STATUS_ERROR

    def mark_error(self, index: int, error: str) -> None:
        item = self._items[index]
        item.error = error
        item.status = STATUS_ERROR

    def approved_items(self) -> list[MessageReviewItem]:
        return [item for item in self._items if item.can_save()]

    def mark_applied(self, applied: Iterable[MessageReviewItem], result: Any = None) -> None:
        result_map = _message_result_map(result)
        fallback_ids = _flatten_record_ids(result)
        for item in applied:
            row_result = result_map.get(item.source_id)
            if row_result is not None:
                errors = _result_errors(row_result)
                if errors:
                    item.error = "; ".join(errors)
                    item.status = STATUS_ERROR
                    continue
                item.created_record_ids = _result_ids(row_result, "created_record_ids")
                item.duplicate_record_ids = _result_ids(row_result, "duplicate_record_ids")
            elif fallback_ids:
                item.created_record_ids = list(fallback_ids)
            item.status = STATUS_APPLIED

    def _resolve_indexes(self, indexes: Iterable[int]) -> list[MessageReviewItem]:
        resolved: list[MessageReviewItem] = []
        for index in indexes:
            if 0 <= index < len(self._items):
                resolved.append(self._items[index])
        return resolved


def _form_with_date(form: Any, achieved_date: date) -> Any:
    updates: dict[str, Any] = {"achieved_date": achieved_date}
    if hasattr(form, "season") and getattr(form, "season", None) is None:
        updates["season"] = achieved_date.year
    try:
        return replace(form, **updates)
    except TypeError:
        for key, value in updates.items():
            setattr(form, key, value)
        return form


def editable_form_values(form: Any) -> dict[str, str]:
    """Return user-editable dataclass values rendered as strings."""
    return editable_field_values(form)


def update_form_values(form: Any, values: dict[str, str]) -> Any:
    if not is_dataclass(form):
        for key, raw_value in values.items():
            current = getattr(form, key, "")
            setattr(form, key, _convert_value(key, raw_value, current))
        return form

    updates: dict[str, Any] = {}
    field_names = {field.name for field in fields(form)}
    for key, raw_value in values.items():
        if key not in field_names:
            continue
        updates[key] = _convert_value(key, raw_value, getattr(form, key))
    try:
        updated = replace(form, **updates)
    except TypeError as exc:
        raise ValueError(str(exc)) from exc
    errors: list[str] = []
    if isinstance(updated, ManualTransferFormData):
        errors = validate_manual_transfer(updated)
    elif isinstance(updated, ManualInjuryFormData):
        errors = validate_manual_injury(updated)
    elif isinstance(updated, ManualMilestoneFormData):
        if updated.target == "player" and not updated.player_id:
            errors.append(tr("Please select a player."))
        if updated.target == "team" and not (updated.team or "").strip():
            errors.append(tr("Please select a team."))
        if not updated.milestone_key:
            errors.append(tr("Please select a milestone."))
    if errors:
        raise ValueError(" ".join(errors))
    return updated


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _convert_value(key: str, raw_value: str, current: Any) -> Any:
    text = raw_value.strip()
    label = display_field(key)
    if isinstance(current, date) or key.endswith("date") or key == "achieved_date":
        if not text:
            raise ValueError(tr("{field}: enter a date.").format(field=label))
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(tr("{field}: use YYYY-MM-DD format.").format(field=label)) from exc
    if current is None:
        if not text:
            return None
        if key.endswith("_id") or key in {"season", "games_at_achievement", "player_id"}:
            return _parse_int(key, text)
        if key in {"achieved_value"}:
            return _parse_float(key, text)
        return text
    if isinstance(current, int) and not isinstance(current, bool):
        if not text:
            raise ValueError(tr("{field}: this field is required.").format(field=label))
        return _parse_int(key, text)
    if isinstance(current, float):
        if not text:
            raise ValueError(tr("{field}: this field is required.").format(field=label))
        return _parse_float(key, text)
    return text


def _parse_int(key: str, text: str) -> int:
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(tr("{field}: enter a whole number.").format(field=display_field(key))) from exc


def _parse_float(key: str, text: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(tr("{field}: enter a number.").format(field=display_field(key))) from exc


def _flatten_record_ids(result: Any) -> list[int]:
    if result is None:
        return []
    if isinstance(result, int):
        return [result]
    if isinstance(result, dict):
        if "record_ids" in result:
            return _flatten_record_ids(result["record_ids"])
        if "id" in result:
            return _flatten_record_ids(result["id"])
        return []
    if isinstance(result, (list, tuple, set)):
        ids: list[int] = []
        for value in result:
            ids.extend(_flatten_record_ids(value))
        return ids
    return []


def _message_result_map(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        if "source_id" in result:
            return {str(result["source_id"]): result}
        for key in ("results", "message_results", "items"):
            if key in result:
                return _message_result_map(result[key])
        return {}
    if isinstance(result, (list, tuple, set)):
        mapped: dict[str, Any] = {}
        for value in result:
            mapped.update(_message_result_map(value))
        return mapped
    source_id = getattr(result, "source_id", None)
    if source_id is not None:
        return {str(source_id): result}
    return {}


def _result_ids(result: Any, key: str) -> list[int]:
    if isinstance(result, dict):
        return _flatten_record_ids(result.get(key, []))
    return _flatten_record_ids(getattr(result, key, []))


def _result_errors(result: Any) -> list[str]:
    errors = result.get("errors", []) if isinstance(result, dict) else getattr(result, "errors", [])
    if isinstance(errors, str):
        return [errors] if errors else []
    if isinstance(errors, (list, tuple, set)):
        return [str(error) for error in errors if str(error)]
    return []
