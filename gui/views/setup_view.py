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
    scan_saves,
)
from gui.widgets.tracked_teams_widget import TrackedTeamsWidget


class SetupView(QWidget):
    """First-run and league selection UI."""

    setup_completed = pyqtSignal(object)  # AppSettings

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
        self._detected_roots: list[DetectedSaveRoot] = []
        self._save_entries: list[SaveEntry] = []
        self._selected_version: int | None = None

        title = QLabel("OOTP Milestone Tracker")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.save_root_input = QLineEdit()
        self.save_root_input.setPlaceholderText("OOTP saved_games 폴더 경로")
        self.browse_button = QPushButton("찾아보기")
        self.browse_button.clicked.connect(self._browse_save_root)

        self.auto_radio = QRadioButton("자동 탐지됨")
        self.manual_radio = QRadioButton("수동 설정")
        self.detection_status = QLabel("")
        self.detection_status.setWordWrap(True)

        self.detected_roots_combo = QComboBox()
        self.detected_roots_combo.setVisible(False)
        self.detected_roots_combo.currentIndexChanged.connect(self._on_detected_root_changed)

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

        self.league_combo = QComboBox()
        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.clicked.connect(self._refresh_leagues)

        league_row = QHBoxLayout()
        league_row.addWidget(self.league_combo, stretch=1)
        league_row.addWidget(self.refresh_button)

        league_group = QGroupBox("리그 선택")
        league_layout = QVBoxLayout(league_group)
        league_layout.addLayout(league_row)

        self.season_spin = QSpinBox()
        self.season_spin.setRange(1900, 2100)
        self.season_spin.setValue(self.settings.current_season)
        self.season_spin.setToolTip(
            "OOTP에서 진행 중인 시즌 연도입니다.\n"
            "박스스코어 임포트·초기값 임포트 필터·마일스톤 판정에 사용됩니다."
        )

        season_group = QGroupBox("현재 시즌")
        season_layout = QFormLayout(season_group)
        season_layout.addRow("시즌 연도:", self.season_spin)
        season_layout.addRow(
            "",
            QLabel("진행 중인 OOTP 시즌과 일치시키세요. (예: 2026 시즌 진행 중 → 2026)"),
        )

        self.tracked_teams_widget = TrackedTeamsWidget(self)
        self.tracked_teams_widget.load_from_settings(self.settings)

        self.season_games_spin = QSpinBox()
        self.season_games_spin.setRange(1, 200)
        self.season_games_spin.setValue(self.settings.season_games_total)

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

        self.korean_names_button = QPushButton("한글 이름 매핑...")
        self.korean_names_button.clicked.connect(self._open_korean_name_mapping)
        self._refresh_korean_names_button()

        names_group = QGroupBox("한글 이름")
        names_layout = QVBoxLayout(names_group)
        names_layout.addWidget(
            QLabel(
                "성·이름 로마자 표기의 한글 매핑을 관리합니다. "
                "스탯·박스스코어 불러오기 후 미등록 항목이 있으면 여기서 입력하세요."
            )
        )
        names_layout.addWidget(self.korean_names_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.selected_path_label = QLabel("")
        self.selected_path_label.setWordWrap(True)
        self.selected_path_label.setStyleSheet("color: #555;")

        self.confirm_button = QPushButton("확인 및 시작")
        self.confirm_button.clicked.connect(self._confirm)
        self.confirm_button.setDefault(True)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addSpacing(12)
        layout.addWidget(save_root_group)
        layout.addWidget(league_group)
        layout.addWidget(season_group)
        layout.addWidget(tracking_group)
        layout.addWidget(names_group)
        layout.addWidget(QLabel("선택된 경로:"))
        layout.addWidget(self.selected_path_label)
        layout.addStretch()
        layout.addWidget(self.confirm_button, alignment=Qt.AlignmentFlag.AlignRight)

        self.save_root_input.textChanged.connect(self._on_save_root_changed)
        self.league_combo.currentIndexChanged.connect(self._update_selected_path_label)
        self.manual_radio.toggled.connect(self._on_mode_changed)

        if embedded and self.settings.active_save_path:
            self.manual_radio.setChecked(True)
            self._restore_saved_values()
        else:
            self._run_auto_detection()
            self._restore_saved_values()

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

    def _open_korean_name_mapping(self) -> None:
        from gui.widgets.korean_name_mapping_dialog import KoreanNameMappingDialog

        dialog = KoreanNameMappingDialog(self)
        dialog.exec()
        self._refresh_korean_names_button()

    def _refresh_korean_names_button(self) -> None:
        from core.roster.korean_names import KoreanNameStore

        count = KoreanNameStore.load().pending_count()
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
