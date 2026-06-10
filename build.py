"""PyInstaller build script for OOTP Milestone Tracker."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
APP_NAME = "ootp_milestone_tracker"


def read_version() -> str:
    version_file = ROOT / "version.txt"
    if not version_file.exists():
        return "0.0.0"
    return version_file.read_text(encoding="utf-8").strip()


def ensure_default_data() -> None:
    """Copy default JSON templates into data/ before building."""
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    settings_example = data_dir / "settings.json.example"
    settings_target = data_dir / "settings.json"
    if settings_example.exists() and not settings_target.exists():
        shutil.copy2(settings_example, settings_target)


def build() -> None:
    version = read_version()
    ensure_default_data()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        APP_NAME,
        "--windowed",
        "--noconfirm",
        "--add-data",
        f"data/milestones.json{';' if sys.platform == 'win32' else ':'}data",
        "--add-data",
        f"data/settings.json.example{';' if sys.platform == 'win32' else ':'}data",
        "main.py",
    ]

    icon_path = ROOT / "assets" / "icon.ico"
    if icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])

    print(f"Building {APP_NAME} v{version}...")
    subprocess.run(cmd, cwd=ROOT, check=True)
    package_release(version)


def package_release(version: str) -> None:
    app_dir = DIST_DIR / APP_NAME
    if not app_dir.exists():
        raise FileNotFoundError(f"Expected build output at {app_dir}")

    zip_name = DIST_DIR / f"{APP_NAME}_v{version}.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in app_dir.rglob("*"):
            archive.write(path, path.relative_to(DIST_DIR))

    print(f"Release package created: {zip_name}")


def clean() -> None:
    for path in (BUILD_DIR, DIST_DIR):
        if path.exists():
            shutil.rmtree(path)
    spec_file = ROOT / f"{APP_NAME}.spec"
    if spec_file.exists():
        spec_file.unlink()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean()
    else:
        build()
