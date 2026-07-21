import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QListWidget, QPushButton

from core.app_state import ReadinessItem
from core.config import AppSettings
from core.i18n import set_language
from core.streak.read_model import ActiveStreak
from gui.views import dashboard_view as dashboard_module
from gui.views.dashboard_view import DashboardView
from gui.widgets.readiness_checklist import ReadinessChecklistCard


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class _SettingsManager:
    def save(self, settings: AppSettings) -> None:
        self.saved = settings

    def get_last_boxscore_import_at(self, settings: AppSettings, boxscore_dir: str):
        return None


class _FakeAggregator:
    is_closed = True
    db_path = "fake.db"

    def get_recent_milestone_records(self, limit: int):
        return []


class _FakeOpenAggregator(_FakeAggregator):
    is_closed = False

    def get_recent_milestone_records(self, limit: int):
        return [
            {
                "player_id": 7,
                "full_name": "A. Freeland",
                "short_name": "",
                "team": "SEO",
                "milestone_key": "career_hits",
                "milestone_label": "통산 2,000안타",
                "achieved_date": "2027-05-01",
                "opponent_team": "BUS",
                "season": 2027,
            }
        ]


class _Milestones:
    def get_by_key(self, key: str):
        return SimpleNamespace(label="통산 2,000안타", grade="legendary")


def _settings() -> AppSettings:
    return AppSettings(
        active_save="SuperYukies_V1.0.lg",
        current_season=2027,
        import_state={"last_import_at": "2026-07-16T20:19:00"},
    )


def test_dashboard_ko_copy_removes_reported_english_labels(monkeypatch) -> None:
    set_language("ko")
    app = qapp()
    view = DashboardView(
        _FakeAggregator(),
        _Milestones(),
        _settings(),
        _SettingsManager(),
    )
    app.processEvents()

    texts = [
        widget.text()
        for widget in view.findChildren((QLabel, QPushButton))
        if hasattr(widget, "text")
    ]
    joined = "\n".join(texts)
    assert "Active Streaks" not in joined
    assert "View Ended Streaks" not in joined
    assert "Most recent success" not in joined
    assert "OOTP 기록 관제실" in joined
    assert "진행 중인 연속 기록" in joined
    assert "종료 기록 보기" in joined


def test_dashboard_lists_use_compact_borderless_wrapping_rows(monkeypatch) -> None:
    set_language("ko")
    app = qapp()
    monkeypatch.setattr(
        dashboard_module,
        "get_readiness_items",
        lambda settings, aggregator: [
            ReadinessItem("league", True, "리그 선택", "SuperYukies"),
            ReadinessItem("teams", True, "팀 선택", "SEO"),
            ReadinessItem("init_import", True, "기존 기록", "완료"),
            ReadinessItem("boxscore_import", True, "박스스코어", "완료"),
        ],
    )
    monkeypatch.setattr(
        dashboard_module,
        "list_active_streaks",
        lambda aggregator, season, limit=6: [
            ActiveStreak(
                season=2027,
                player_id=7,
                player_name="A. Freeland",
                team="Seoul Yukies",
                streak_type="hit_streak",
                label="연속 안타",
                unit="games",
                value=9,
                display_value="9",
                start_date="2027-04-01",
                last_date="2027-04-12",
            )
        ],
    )
    view = DashboardView(
        _FakeOpenAggregator(),
        _Milestones(),
        _settings(),
        _SettingsManager(),
    )

    view.refresh_active_streaks()
    view.refresh_recent_achievements()
    app.processEvents()

    assert view.streak_list.objectName() == "dashboardStreakList"
    assert view.near_list.objectName() == "dashboardNearList"
    assert view.streak_list.wordWrap()
    assert view.recent_list.wordWrap()
    assert view.streak_list.item(0).sizeHint().height() >= 58
    assert view.recent_list.item(0).sizeHint().height() >= 50
    assert view.streak_list.itemWidget(view.streak_list.item(0)) is not None
    assert view.recent_list.itemWidget(view.recent_list.item(0)) is not None

    for list_widget in view.findChildren(QListWidget):
        assert "border: none" in list_widget.styleSheet()


def test_readiness_complete_state_is_compact_chip() -> None:
    set_language("ko")
    app = qapp()
    card = ReadinessChecklistCard()
    card.set_items(
        [
            ReadinessItem("league", True, "리그", "완료"),
            ReadinessItem("teams", True, "팀", "완료"),
        ]
    )
    app.processEvents()

    chip = card.findChild(type(card._collapsed_chip), "readinessCompleteChip")
    assert chip is not None
    assert chip.isVisible() is False  # parent not shown in offscreen tests
    assert card._collapsed_chip.isHidden() is False
    assert card._card.isHidden()
