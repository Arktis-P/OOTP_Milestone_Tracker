"""Internationalization (i18n) public API."""

from core.i18n.translator import get_language, set_language, tr

__all__ = ["tr", "set_language", "get_language"]
