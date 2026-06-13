"""Application configuration package."""

from core.config.path_detector import DetectedSaveRoot, detect_save_roots, infer_ootp_version_from_path, is_valid_save_root
from core.config.save_scanner import SaveEntry, find_save_by_name, is_valid_league_folder, scan_saves
from core.config.paths import (
    default_settings_path,
    ensure_user_data_dir,
    get_bundle_root,
    get_project_root,
    get_user_data_dir,
    resolve_data_path,
)
from core.config.settings_manager import (
    AppSettings,
    SettingsManager,
    load_settings,
)

__all__ = [
    "AppSettings",
    "DetectedSaveRoot",
    "SaveEntry",
    "SettingsManager",
    "default_settings_path",
    "detect_save_roots",
    "ensure_user_data_dir",
    "find_save_by_name",
    "get_bundle_root",
    "get_project_root",
    "get_user_data_dir",
    "infer_ootp_version_from_path",
    "is_valid_league_folder",
    "is_valid_save_root",
    "load_settings",
    "resolve_data_path",
    "scan_saves",
]
