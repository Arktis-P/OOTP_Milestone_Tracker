"""OOTP Milestone Tracker — application entry point."""


def main() -> None:
    # Load settings and set language BEFORE importing any GUI module.
    # All module-level tr() calls in GUI files are resolved at import time,
    # so set_language() must run first.
    from core.config import SettingsManager
    from core.i18n import set_language

    settings = SettingsManager().load()
    set_language(settings.language)

    from gui.app import run_app
    run_app()


if __name__ == "__main__":
    main()
