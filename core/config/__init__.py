"""Application configuration package."""

from core.config.path_detector import DetectedSaveRoot, detect_save_roots, infer_ootp_version_from_path, is_valid_save_root
from core.config.save_scanner import SaveEntry, find_save_by_name, is_valid_league_folder, scan_saves
from core.config.settings_manager import (
    AppSettings,
    SettingsManager,
    default_settings_path,
    get_project_root,
    load_settings,
    resolve_data_path,
)

__all__ = [
    "AppSettings",
    "DetectedSaveRoot",
    "SaveEntry",
    "SettingsManager",
    "default_settings_path",
    "detect_save_roots",
    "find_save_by_name",
    "infer_ootp_version_from_path",
    "is_valid_league_folder",
    "is_valid_save_root",
    "load_settings",
    "resolve_data_path",
    "scan_saves",
]
