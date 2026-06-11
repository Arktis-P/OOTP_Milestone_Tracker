"""Initial career stats import tab."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import AppSettings, SettingsManager
from core.stats.aggregator import Aggregator
from core.stats.initial_import import InitialImporter


class InitialImportView(QWidget):
    def __init__(
        self,
        aggregator: Aggregator,
        settings: AppSettings,
        settings_manager: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.settings = settings
        self.settings_manager = settings_manager
        self.importer = InitialImporter(aggregator)

        self.dir_input = QLineEdit(self.settings.initial_stats_dir)
        self.dir_input.setPlaceholderText("player_batting_stats.txt / player_pitching_stats.txt 폴더")
        browse_button = QPushButton("찾아보기")
        browse_button.clicked.connect(self._browse_dir)

        self.status_label = QLabel()
        self._update_status()

        batting_button = QPushButton("타격 초기값 가져오기")
        pitching_button = QPushButton("투구 초기값 가져오기")
        both_button = QPushButton("폴더 내 전체 가져오기")
        batting_button.clicked.connect(self._import_batting)
        pitching_button.clicked.connect(self._import_pitching)
        both_button.clicked.connect(self._import_both)

        dir_row = QHBoxLayout()
        dir_row.addWidget(self.dir_input, stretch=1)
        dir_row.addWidget(browse_button)

        button_row = QHBoxLayout()
        button_row.addWidget(batting_button)
        button_row.addWidget(pitching_button)
        button_row.addWidget(both_button)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("프로그램 도입 이전 통산 기록 (OOTP player_*_stats.txt)"))
        layout.addLayout(dir_row)
        layout.addLayout(button_row)
        layout.addWidget(self.status_label)
        layout.addStretch()

    def _browse_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "초기값 통계 폴더 선택",
            self.dir_input.text() or str(Path.home()),
        )
        if selected:
            self.dir_input.setText(selected)
            self._save_dir(selected)

    def _save_dir(self, directory: str) -> None:
        self.settings.initial_stats_dir = directory
        self.settings_manager.save(self.settings)

    def _import_batting(self) -> None:
        path = self._pick_file("player_batting_stats.txt")
        if not path:
            return
        result = self.importer.import_batting(path)
        self._show_result("타격 초기값", result.imported, result.errors)

    def _import_pitching(self) -> None:
        path = self._pick_file("player_pitching_stats.txt")
        if not path:
            return
        result = self.importer.import_pitching(path)
        self._show_result("투구 초기값", result.imported, result.errors)

    def _import_both(self) -> None:
        directory = self.dir_input.text().strip()
        if not directory:
            QMessageBox.warning(self, "경로 필요", "초기값 폴더를 지정하세요.")
            return
        self._save_dir(directory)
        result = self.importer.import_from_settings_dir(directory)
        self._show_result("초기값", result.imported, result.errors)

    def _pick_file(self, default_name: str) -> Path | None:
        directory = self.dir_input.text().strip()
        start = str(Path(directory) / default_name) if directory else default_name
        selected, _ = QFileDialog.getOpenFileName(
            self,
            f"{default_name} 선택",
            start,
            "Text files (*.txt);;All files (*)",
        )
        if not selected:
            return None
        path = Path(selected)
        self.dir_input.setText(str(path.parent))
        self._save_dir(str(path.parent))
        return path

    def _show_result(self, label: str, imported: int, errors: list[str]) -> None:
        self._update_status()
        if errors:
            QMessageBox.warning(
                self,
                label,
                f"{imported}건 저장됨\n\n오류:\n" + "\n".join(errors[:8]),
            )
        else:
            QMessageBox.information(self, label, f"{imported}건 저장되었습니다.")

    def _update_status(self) -> None:
        summary = self.importer.get_init_summary()
        self.status_label.setText(
            f"타격 초기값: {summary['batting_players']:,}명 · "
            f"투구 초기값: {summary['pitching_players']:,}명"
        )
