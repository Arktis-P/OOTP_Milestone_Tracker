"""Initial OOTP save folder and league selection screen."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QFrame,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import (
    AppSettings,
    DetectedSaveRoot,
    SaveEntry,
    SettingsManager,
    detect_save_roots,
    infer_ootp_version_from_path,
    is_valid_save_root,
    resolve_data_path,
    scan_saves,
)
from core.db.reset import (
    format_save_data_summary,
    reset_save_database,
    summarize_save_database,
)
from gui.widgets.tracked_teams_widget import TrackedTeamsWidget
from gui.widgets.card_panel import CardPanel, section_label, tool_row
from gui.theme import SLATE_500, TEXT_MUTED


class SetupView(QWidget):
    """First-run and league selection UI."""

    setup_completed = pyqtSignal(object)  # AppSettings
    milestones_changed = pyqtSignal()
    bundle_updates_changed = pyqtSignal()
    save_database_reset_prepare = pyqtSignal()
    save_database_reset = pyqtSignal()
    boxscore_reimported = pyqtSignal(str)

    def __init__(
        self,
        settings_manager: SettingsManager,
        settings: AppSettings | None = None,
        parent: QWidget | None = None,
        *,
        embedded: bool = False,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.settings = settings or settings_manager.load()
        self._embedded = embedded
        self._detected_roots: list[DetectedSaveRoot] = []
        self._save_entries: list[SaveEntry] = []
        self._selected_version: int | None = None

        title = QLabel("OOTP Milestone Tracker")
        title.setObjectName("pageTitle")

        self.save_root_input = QLineEdit()
        self.save_root_input.setPlaceholderText("OOTP saved_games 폴더 경로")
        self.browse_button = QPushButton("경로 확인" if embedded else "찾아보기")
        self.browse_button.clicked.connect(self._browse_save_root)

        self.auto_radio = QRadioButton("자동 탐지됨")
        self.manual_radio = QRadioButton("수동 설정")
        self.detection_status = QLabel("")
        self.detection_status.setWordWrap(True)
        self.detection_status.setObjectName("mutedLabel")

        self.detected_roots_combo = QComboBox()
        self.detected_roots_combo.setVisible(False)
        self.detected_roots_combo.currentIndexChanged.connect(self._on_detected_root_changed)

        self.league_combo = QComboBox()
        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.clicked.connect(self._refresh_leagues)

        self.season_spin = QSpinBox()
        self.season_spin.setRange(1900, 2100)
        self.season_spin.setValue(self.settings.current_season)
        self.season_spin.setToolTip(
            "OOTP에서 진행 중인 시즌 연도입니다.\n"
            "박스스코어 임포트·초기값 임포트 필터·마일스톤 판정에 사용됩니다."
        )

        self.tracked_teams_widget = TrackedTeamsWidget(
            self, checkbox_mode=embedded
        )
        self.tracked_teams_widget.load_from_settings(self.settings)

        self.season_games_spin = QSpinBox()
        self.season_games_spin.setRange(1, 200)
        self.season_games_spin.setValue(self.settings.season_games_total)

        self.korean_names_button = QPushButton("매핑 대기 열기")
        self.korean_names_button.clicked.connect(self._open_korean_name_mapping)
        self.korean_badge = QLabel("0")
        self.korean_badge.setObjectName("badgeLabel")
        self.korean_badge.setVisible(False)
        self._refresh_korean_names_button()

        self.bundle_updates_status = QLabel()
        self.bundle_updates_status.setWordWrap(True)
        self.bundle_updates_status.setObjectName("mutedLabel")
        self.bundle_updates_button = QPushButton("병합 업데이트 실행")
        self.bundle_updates_button.clicked.connect(self._open_bundle_updates)

        self.milestones_button = QPushButton("기준 테이블 편집")
        self.milestones_button.clicked.connect(self._open_milestone_definitions)

        self.selected_path_label = QLabel("")
        self.selected_path_label.setWordWrap(True)
        self.selected_path_label.setObjectName("mutedLabel")

        self.confirm_button = QPushButton(
            "설정 일괄 저장 & 데이터 리프레시" if embedded else "확인 및 시작"
        )
        self.confirm_button.clicked.connect(self._confirm)
        self.confirm_button.setDefault(True)
        if embedded:
            self.confirm_button.setObjectName("primaryButton")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        if not embedded:
            layout.addWidget(title)
            layout.addSpacing(4)
            self._build_first_run_layout(layout)
        else:
            self._build_embedded_layout(layout)

        self.save_root_input.textChanged.connect(self._on_save_root_changed)
        self.league_combo.currentIndexChanged.connect(self._update_selected_path_label)
        self.manual_radio.toggled.connect(self._on_mode_changed)

        if embedded and self.settings.active_save_path:
            self.manual_radio.setChecked(True)
            self._restore_saved_values()
        else:
            self._run_auto_detection()
            self._restore_saved_values()

        self.refresh_bundle_updates_status()

    def _build_first_run_layout(self, layout: QVBoxLayout) -> None:
        save_root_row = QHBoxLayout()
        save_root_row.addWidget(self.save_root_input, stretch=1)
        save_root_row.addWidget(self.browse_button)

        save_root_group = QGroupBox("OOTP 세이브 폴더")
        save_root_layout = QVBoxLayout(save_root_group)
        save_root_layout.addLayout(save_root_row)
        save_root_layout.addWidget(self.detected_roots_combo)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.auto_radio)
        mode_row.addWidget(self.manual_radio)
        mode_row.addStretch()
        save_root_layout.addLayout(mode_row)
        save_root_layout.addWidget(self.detection_status)

        league_row = QHBoxLayout()
        league_row.addWidget(self.league_combo, stretch=1)
        league_row.addWidget(self.refresh_button)
        league_group = QGroupBox("리그 선택")
        league_layout = QVBoxLayout(league_group)
        league_layout.addLayout(league_row)

        season_group = QGroupBox("현재 시즌")
        season_layout = QFormLayout(season_group)
        season_layout.addRow("시즌 연도:", self.season_spin)
        season_layout.addRow(
            "",
            QLabel("진행 중인 OOTP 시즌과 일치시키세요. (예: 2026 시즌 진행 중 → 2026)"),
        )

        tracking_group = QGroupBox("추적 설정")
        tracking_layout = QFormLayout(tracking_group)
        tracking_layout.addRow("추적 팀:", self.tracked_teams_widget)
        tracking_layout.addRow("시즌 총 경기:", self.season_games_spin)
        tracking_layout.addRow(
            "",
            QLabel(
                "MLB 30개 팀 중 선택하거나 수동으로 추가하세요. "
                "게임에 확장 팀 등 신규 MLB 구단이 추가된 경우에만 "
                "초기값 임포트 시 추가 여부를 묻습니다."
            ),
        )

        names_group = QGroupBox("한글 이름")
        names_layout = QVBoxLayout(names_group)
        names_layout.addWidget(
            QLabel(
                "성·이름 로마자 표기의 한글 매핑을 관리합니다. "
                "스탯·박스스코어 불러오기 후 미등록 항목이 있으면 여기서 입력하세요."
            )
        )
        names_layout.addWidget(self.korean_names_button)

        bundle_group = QGroupBox("기준 파일 업데이트")
        bundle_layout = QVBoxLayout(bundle_group)
        bundle_layout.addWidget(
            QLabel(
                "앱 업데이트 후 추가된 마일스톤·연속기록·한글 매핑 항목을 "
                "로컬 파일에 병합합니다."
            )
        )
        bundle_layout.addWidget(self.bundle_updates_status)
        bundle_layout.addWidget(self.bundle_updates_button)

        milestones_group = QGroupBox("마일스톤 기준")
        milestones_layout = QVBoxLayout(milestones_group)
        milestones_layout.addWidget(
            QLabel("달성 판정에 사용되는 마일스톤 목록을 milestones.csv에서 관리합니다.")
        )
        milestones_layout.addWidget(self.milestones_button)

        layout.addWidget(save_root_group)
        layout.addWidget(league_group)
        layout.addWidget(season_group)
        layout.addWidget(tracking_group)
        layout.addWidget(names_group)
        layout.addWidget(bundle_group)
        layout.addWidget(milestones_group)
        layout.addWidget(QLabel("선택된 경로:"))
        layout.addWidget(self.selected_path_label)
        layout.addStretch()
        layout.addWidget(self.confirm_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _build_embedded_layout(self, layout: QVBoxLayout) -> None:
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(section_label("OOTP SAVED_GAMES 기본 루트"), stretch=0)
        path_row.addWidget(self.save_root_input, stretch=1)
        path_row.addWidget(self.browse_button)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.auto_radio)
        mode_row.addWidget(self.manual_radio)
        mode_row.addStretch()

        league_season_row = QHBoxLayout()
        league_season_row.setSpacing(12)
        league_col = QVBoxLayout()
        league_col.setSpacing(4)
        league_col.addWidget(section_label("스캔된 세이브 리그"))
        league_btns = QHBoxLayout()
        league_btns.addWidget(self.league_combo, stretch=1)
        league_btns.addWidget(self.refresh_button)
        league_col.addLayout(league_btns)
        season_col = QVBoxLayout()
        season_col.setSpacing(4)
        season_col.addWidget(section_label("현재 활성 시즌"))
        season_col.addWidget(self.season_spin)
        league_season_row.addLayout(league_col, stretch=1)
        league_season_row.addLayout(season_col, stretch=0)

        teams_header = QHBoxLayout()
        teams_header.addWidget(section_label("추적 대상 구단 리스트"))
        teams_header.addStretch()
        add_team_link = QPushButton("+ 팀 수동 추가")
        add_team_link.setObjectName("linkButton")
        add_team_link.clicked.connect(self.tracked_teams_widget.add_custom_team_dialog)
        teams_header.addWidget(add_team_link)

        season_games_row = QHBoxLayout()
        season_games_row.setSpacing(8)
        season_games_row.addWidget(section_label("시즌 총 경기수"))
        season_games_row.addWidget(self.season_games_spin)
        season_games_row.addStretch()

        ootp_card = CardPanel("📁  OOTP 연동 설정")
        ootp_card.content_layout.addLayout(path_row)
        ootp_card.content_layout.addWidget(self.detected_roots_combo)
        ootp_card.content_layout.addLayout(mode_row)
        ootp_card.content_layout.addWidget(self.detection_status)
        ootp_card.content_layout.addLayout(league_season_row)
        ootp_card.content_layout.addLayout(teams_header)
        ootp_card.content_layout.addWidget(self.tracked_teams_widget)
        ootp_card.content_layout.addLayout(season_games_row)
        ootp_card.content_layout.addWidget(self.selected_path_label)

        self._init_db_reset_widgets()

        tools_card = CardPanel("🛠️  고급 모듈 및 데이터 도구")
        tools_card.add_widget(
            tool_row(
                "한글 이름 자동 매핑",
                "로마자 성·이름 한글 변환 대기 중인 항목을 처리합니다.",
                self.korean_names_button,
                badge=self.korean_badge,
            )
        )
        tools_card.add_widget(
            tool_row(
                "마일스톤 기준 조건 수정",
                "milestones.csv 마일스톤 종류 및 등급 판단 수치를 정의합니다.",
                self.milestones_button,
            )
        )
        tools_card.add_widget(
            tool_row(
                "앱 기준 파일 업데이트",
                "로컬 마일스톤 룰셋과 한글 매핑 패치를 병합합니다.",
                self.bundle_updates_button,
            )
        )
        tools_card.add_widget(self._build_dev_tools_panel())

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(ootp_card, stretch=1)
        columns.addWidget(tools_card, stretch=1)
        layout.addLayout(columns, stretch=1)
        layout.addWidget(self.confirm_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _init_db_reset_widgets(self) -> None:
        self.db_summary_label = QLabel()
        self.db_summary_label.setWordWrap(True)
        self.db_summary_label.setObjectName("mutedLabel")
        self.db_path_label = QLabel()
        self.db_path_label.setWordWrap(True)
        self.db_path_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.refresh_db_summary_button = QPushButton("현황 새로고침")
        self.refresh_db_summary_button.clicked.connect(self._refresh_database_summary)
        self.reset_db_button = QPushButton("🚨 DB 완전 초기화")
        self.reset_db_button.setObjectName("dangerButton")
        self.reset_db_button.clicked.connect(self._reset_save_database)
        self.dev_reimport_button = QPushButton("🔄 박스스코어 개별 재임포트")
        self.dev_reimport_button.clicked.connect(self._open_dev_boxscore_reimport)
        self._refresh_database_summary()

    def _build_dev_tools_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("toolRow")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        dev_title = QLabel("개발 도구 (Developer Menu)")
        dev_title.setObjectName("toolRowTitle")
        layout.addWidget(dev_title)

        dev_buttons = QHBoxLayout()
        dev_buttons.setSpacing(8)
        dev_buttons.addWidget(self.dev_reimport_button, stretch=1)
        dev_buttons.addWidget(self.reset_db_button)
        layout.addLayout(dev_buttons)

        layout.addWidget(self.db_summary_label)
        layout.addWidget(self.db_path_label)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        refresh_row.addWidget(self.refresh_db_summary_button)
        layout.addLayout(refresh_row)
        return panel

    def refresh_bundle_updates_status(self) -> None:
        from core.config.bundle_updates import scan_pending_updates

        report = scan_pending_updates()
        if report.total:
            self.bundle_updates_status.setText(
                f"받을 수 있는 새 항목 {report.total}건 "
                f"(앱 v{report.app_version})"
            )
            self.bundle_updates_status.setStyleSheet("color: #c0392b;")
            self.bundle_updates_button.setEnabled(True)
            if self._embedded:
                self.bundle_updates_button.setText("병합 업데이트 실행")
                self.bundle_updates_button.setObjectName("dangerButton")
            else:
                self.bundle_updates_button.setText(
                    f"기준 파일 업데이트... ({report.total})"
                )
                self.bundle_updates_button.setObjectName("")
        else:
            self.bundle_updates_status.setText("모든 기준 파일이 최신입니다.")
            self.bundle_updates_status.setStyleSheet(f"color: {SLATE_500};")
            self.bundle_updates_button.setEnabled(False)
            if self._embedded:
                self.bundle_updates_button.setText("병합 업데이트 실행")
            else:
                self.bundle_updates_button.setText("기준 파일 업데이트...")
            self.bundle_updates_button.setObjectName("")
        self.bundle_updates_button.style().unpolish(self.bundle_updates_button)
        self.bundle_updates_button.style().polish(self.bundle_updates_button)

    def _run_auto_detection(self) -> None:
        self._detected_roots = detect_save_roots()
        if not self._detected_roots:
            self.auto_radio.setEnabled(False)
            self.manual_radio.setChecked(True)
            self.detection_status.setText(
                "자동 탐지에 실패했습니다. [찾아보기]로 saved_games 폴더를 직접 선택하세요."
            )
            return

        self.auto_radio.setEnabled(True)
        self.auto_radio.setChecked(True)
        self.detection_status.setText(
            f"자동 탐지 성공: {len(self._detected_roots)}개 경로를 찾았습니다."
        )

        if len(self._detected_roots) > 1:
            self.detected_roots_combo.setVisible(True)
            self.detected_roots_combo.blockSignals(True)
            self.detected_roots_combo.clear()
            for item in self._detected_roots:
                self.detected_roots_combo.addItem(
                    f"OOTP {item.ootp_version} — {item.path}",
                    str(item.path),
                )
            self.detected_roots_combo.blockSignals(False)
        else:
            self.detected_roots_combo.setVisible(False)

        if not self.settings.ootp_save_root:
            first = self._detected_roots[0]
            self._apply_save_root(str(first.path), first.ootp_version, from_auto=True)

    def _restore_saved_values(self) -> None:
        if self.settings.ootp_save_root:
            if is_valid_save_root(self.settings.ootp_save_root):
                self.manual_radio.setChecked(True)
                self.save_root_input.setText(self.settings.ootp_save_root)
            else:
                self.save_root_input.setText(self.settings.ootp_save_root)

        self._refresh_leagues()

        if self.settings.active_save:
            index = self.league_combo.findText(self.settings.active_save)
            if index >= 0:
                self.league_combo.setCurrentIndex(index)

        self.season_spin.setValue(self.settings.current_season)
        self.season_games_spin.setValue(self.settings.season_games_total)
        self.tracked_teams_widget.load_from_settings(self.settings)

    def _browse_save_root(self) -> None:
        start_dir = self.save_root_input.text().strip() or str(Path.home() / "Documents")
        selected = QFileDialog.getExistingDirectory(
            self,
            "OOTP saved_games 폴더 선택",
            start_dir,
        )
        if not selected:
            return

        self.manual_radio.setChecked(True)
        self.save_root_input.setText(selected)
        self._validate_and_refresh(selected, show_errors=True)

    def _on_mode_changed(self, manual: bool) -> None:
        if not manual and self._detected_roots:
            index = self.detected_roots_combo.currentIndex()
            if index >= 0 and self.detected_roots_combo.isVisible():
                self._on_detected_root_changed(index)
            else:
                first = self._detected_roots[0]
                self._apply_save_root(str(first.path), first.ootp_version, from_auto=True)

    def _on_detected_root_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._detected_roots):
            return
        if not self.auto_radio.isChecked():
            return
        item = self._detected_roots[index]
        self._apply_save_root(str(item.path), item.ootp_version, from_auto=True)

    def _on_save_root_changed(self, text: str) -> None:
        if self.manual_radio.isChecked():
            self._validate_and_refresh(text.strip(), show_errors=False)

    def _apply_save_root(self, path: str, version: int | None, *, from_auto: bool) -> None:
        self.save_root_input.blockSignals(True)
        self.save_root_input.setText(path)
        self.save_root_input.blockSignals(False)
        self._selected_version = version
        if from_auto:
            self.detection_status.setText(f"자동 탐지됨: OOTP {version} — {path}")
        self._refresh_leagues()

    def _validate_and_refresh(self, path: str, *, show_errors: bool) -> None:
        if not path:
            self.league_combo.clear()
            self._save_entries = []
            self._update_selected_path_label()
            return

        if not is_valid_save_root(path):
            self.league_combo.clear()
            self._save_entries = []
            self._update_selected_path_label()
            if show_errors:
                QMessageBox.warning(
                    self,
                    "유효하지 않은 경로",
                    "선택한 폴더가 OOTP saved_games 디렉토리가 아닙니다.\n\n"
                    "saved_games 폴더를 선택했는지 확인하세요.\n"
                    "(하위에 리그 폴더 또는 .lg 폴더가 있어야 합니다.)",
                )
            else:
                self.detection_status.setText("유효하지 않은 saved_games 경로입니다.")
            return

        self._selected_version = None
        self.detection_status.setText("유효한 saved_games 경로입니다.")
        self._refresh_leagues()

    def _refresh_leagues(self) -> None:
        path = self.save_root_input.text().strip()
        if not path or not is_valid_save_root(path):
            self.league_combo.clear()
            self._save_entries = []
            self._update_selected_path_label()
            return

        self._save_entries = scan_saves(path)
        previous = self.league_combo.currentText()

        self.league_combo.blockSignals(True)
        self.league_combo.clear()
        for entry in self._save_entries:
            self.league_combo.addItem(entry.name, str(entry.path))
        self.league_combo.blockSignals(False)

        if not self._save_entries:
            self.detection_status.setText("saved_games 아래에서 유효한 리그 폴더를 찾지 못했습니다.")
            self._update_selected_path_label()
            return

        restore_index = self.league_combo.findText(previous)
        if restore_index >= 0:
            self.league_combo.setCurrentIndex(restore_index)
        elif self.settings.active_save:
            saved_index = self.league_combo.findText(self.settings.active_save)
            if saved_index >= 0:
                self.league_combo.setCurrentIndex(saved_index)

        self._update_selected_path_label()

    def _update_selected_path_label(self) -> None:
        index = self.league_combo.currentIndex()
        if index >= 0:
            path = self.league_combo.itemData(index)
            self.selected_path_label.setText(str(path) if path else "")
        else:
            self.selected_path_label.setText("(리그를 선택하세요)")
        if hasattr(self, "db_summary_label"):
            self._refresh_database_summary()

    def _open_dev_boxscore_reimport(self) -> None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            QMessageBox.warning(
                self, "리그 필요", "다시 불러올 리그를 먼저 선택하세요."
            )
            return

        db_path = resolve_data_path(settings.db_path)
        from gui.widgets.dev_boxscore_reimport_dialog import DevBoxscoreReimportDialog

        dialog = DevBoxscoreReimportDialog(
            settings_manager=self.settings_manager,
            settings=settings,
            db_path=db_path,
            parent=self,
        )
        dialog.exec()
        if dialog.result_message:
            self.boxscore_reimported.emit(dialog.result_message)

    def _current_db_path(self) -> Path | None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            return None
        return resolve_data_path(settings.db_path)

    def _refresh_database_summary(self) -> None:
        db_path = self._current_db_path()
        if db_path is None:
            self.db_summary_label.setText("리그를 선택하면 DB 현황이 표시됩니다.")
            self.db_path_label.setText("")
            self.reset_db_button.setEnabled(False)
            return

        summary = summarize_save_database(db_path)
        if summary.has_data:
            self.db_summary_label.setText(format_save_data_summary(summary))
        else:
            self.db_summary_label.setText("저장된 경기·마일스톤·초기값 데이터가 없습니다.")
        self.db_path_label.setText(f"DB: {db_path}")
        self.reset_db_button.setEnabled(True)

    def _reset_save_database(self) -> None:
        settings = self.settings_manager.ensure_derived_paths(self.settings)
        if not settings.active_save_path:
            QMessageBox.warning(self, "리그 필요", "초기화할 리그를 먼저 선택하세요.")
            return

        db_path = resolve_data_path(settings.db_path)
        summary = summarize_save_database(db_path)
        save_name = settings.active_save or "현재 세이브"
        detail = format_save_data_summary(summary) if summary.has_data else "저장된 데이터 없음"

        reply = QMessageBox.warning(
            self,
            "데이터 초기화",
            (
                f"「{save_name}」 세이브의 추적 데이터를 모두 삭제합니다.\n\n"
                f"{detail}\n\n"
                "마일스톤 기록, 시즌/통산 기록, 예측 목록이 삭제되며 "
                "되돌릴 수 없습니다. 계속하시겠습니까?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.save_database_reset_prepare.emit()
            reset_save_database(db_path)
        except OSError as exc:
            self.save_database_reset.emit()
            QMessageBox.critical(
                self,
                "초기화 실패",
                f"DB 파일을 삭제하지 못했습니다.\n{exc}",
            )
            return
        except Exception as exc:
            self.save_database_reset.emit()
            QMessageBox.critical(self, "초기화 실패", str(exc))
            return

        settings.import_state = {"boxscore_dir": "", "last_import_at": ""}
        self.settings = settings
        self.settings_manager.save(settings)
        self._refresh_database_summary()
        self.save_database_reset.emit()
        QMessageBox.information(
            self,
            "초기화 완료",
            "현재 세이브 데이터를 초기화했습니다.\n"
            "초기값 설정과 박스스코어 가져오기를 다시 진행하세요.",
        )

    def _open_korean_name_mapping(self) -> None:
        from gui.widgets.korean_name_mapping_dialog import KoreanNameMappingDialog

        dialog = KoreanNameMappingDialog(self)
        dialog.exec()
        self._refresh_korean_names_button()

    def _open_bundle_updates(self) -> None:
        from core.config.bundle_updates import apply_bundle_updates_with_message

        if apply_bundle_updates_with_message(self):
            self._on_bundle_updates_applied()

    def _on_bundle_updates_applied(self) -> None:
        self.refresh_bundle_updates_status()
        self.milestones_changed.emit()
        self.bundle_updates_changed.emit()

    def _open_milestone_definitions(self) -> None:
        from gui.widgets.milestone_definitions_dialog import MilestoneDefinitionsDialog

        path = resolve_data_path(self.settings.milestones_path)
        dialog = MilestoneDefinitionsDialog(path, self)
        dialog.definitions_changed.connect(self.milestones_changed.emit)
        dialog.exec()

    def _refresh_korean_names_button(self) -> None:
        from core.roster.korean_names import KoreanNameStore

        count = KoreanNameStore.load().pending_count()
        if self._embedded:
            self.korean_badge.setText(str(count) if count else "0")
            self.korean_badge.setVisible(bool(count))
            self.korean_names_button.setText("매핑 대기 열기")
        else:
            text = "한글 이름 매핑..."
            if count:
                text += f" ({count})"
            self.korean_names_button.setText(text)

    def _confirm(self) -> None:
        save_root = self.save_root_input.text().strip()
        if not save_root:
            QMessageBox.warning(self, "입력 필요", "OOTP 세이브 폴더를 선택하세요.")
            return

        if not is_valid_save_root(save_root):
            QMessageBox.warning(
                self,
                "유효하지 않은 경로",
                "OOTP saved_games 폴더가 아닙니다. 경로를 다시 확인하세요.",
            )
            return

        index = self.league_combo.currentIndex()
        if index < 0:
            QMessageBox.warning(self, "리그 선택 필요", "리그를 선택하세요.")
            return

        save_name = self.league_combo.currentText()
        save_path = str(self.league_combo.itemData(index))

        ootp_version = self._selected_version or infer_ootp_version_from_path(save_root)
        if ootp_version is None:
            ootp_version = self.settings.ootp_version

        updated = self.settings_manager.update_active_save(
            self.settings,
            save_root=save_root,
            save_name=save_name,
            save_path=save_path,
            ootp_version=ootp_version,
        )
        updated.current_season = self.season_spin.value()
        updated.season_games_total = self.season_games_spin.value()
        self.tracked_teams_widget.apply_to_settings(updated)
        self.settings_manager.save(updated)
        self.setup_completed.emit(updated)
