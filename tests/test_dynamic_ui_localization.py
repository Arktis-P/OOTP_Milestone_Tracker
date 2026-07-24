from __future__ import annotations

from core.i18n import tr
from core.i18n.translator import set_language
from gui.widgets.guided_milestone_form import (
    CATEGORY_DISPLAY_KEYS,
    FIELD_DISPLAY_KEYS,
    REASON_DISPLAY_KEYS,
    SOURCE_DISPLAY_KEYS,
    STATUS_DISPLAY_KEYS,
    display_category,
    display_field,
    display_reason,
    display_source,
    display_status,
)


def test_dynamic_message_review_labels_have_korean_translations() -> None:
    set_language("ko")
    try:
        for source in (
            CATEGORY_DISPLAY_KEYS,
            REASON_DISPLAY_KEYS,
            STATUS_DISPLAY_KEYS,
            SOURCE_DISPLAY_KEYS,
            FIELD_DISPLAY_KEYS,
        ):
            for display_key in source.values():
                assert tr(display_key) != display_key
    finally:
        set_language("ko")


def test_dynamic_helpers_do_not_expose_enum_codes_in_korean_mode() -> None:
    set_language("ko")
    try:
        assert display_category("award_mvp") != "award_mvp"
        assert display_reason("message_date_required") != "message_date_required"
        assert display_status("date_needed") != "date_needed"
        assert display_source("message_auto") != "message_auto"
        assert display_field("milestone_key") != "milestone_key"
    finally:
        set_language("ko")


def test_dynamic_helpers_keep_natural_english_in_english_mode() -> None:
    set_language("en")
    try:
        assert display_category("award_mvp") == "Most Valuable Player award"
        assert display_reason("message_date_required") == "Message date is required before saving."
        assert display_status("date_needed") == "Date needed"
        assert display_source("message_auto") == "Message automatic"
        assert display_field("milestone_key") == "Record type"
    finally:
        set_language("ko")
