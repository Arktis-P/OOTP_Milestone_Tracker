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
ASSETS_DIR = ROOT / "assets"
ICON_SOURCE = ROOT / "icon.png"
ICON_PNG = ASSETS_DIR / "icon.png"
ICON_ICO = ASSETS_DIR / "icon.ico"

# Default templates bundled into _MEIPASS/data/; copied to user data dir on first run.
BUNDLE_DATA_FILES = (
    "milestones.csv",
    "settings.json.example",
    "korean_last_names.csv",
    "korean_first_names.csv",
    "korean_names_pending.csv.example",
    "streak_policies.json",
)


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

    pending_example = data_dir / "korean_names_pending.csv.example"
    pending_target = data_dir / "korean_names_pending.csv"
    if pending_example.exists() and not pending_target.exists():
        shutil.copy2(pending_example, pending_target)


def _pyinstaller_add_data(relative_path: str, *, dest_dir: str = "data") -> str:
    sep = ";" if sys.platform == "win32" else ":"
    return f"{relative_path}{sep}{dest_dir}"


def ensure_app_icon() -> Path:
    """Copy icon.png into assets/ and build a multi-size Windows .ico."""
    ASSETS_DIR.mkdir(exist_ok=True)
    source = ICON_SOURCE if ICON_SOURCE.is_file() else ICON_PNG
    if not source.is_file():
        raise FileNotFoundError(
            f"App icon not found. Expected {ICON_SOURCE} or {ICON_PNG}."
        )

    if source.resolve() != ICON_PNG.resolve():
        shutil.copy2(source, ICON_PNG)

    from PIL import Image

    img = Image.open(ICON_PNG).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ICON_ICO, format="ICO", sizes=sizes)
    return ICON_ICO


def build() -> None:
    version = read_version()
    ensure_default_data()
    icon_path = ensure_app_icon()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        APP_NAME,
        "--windowed",
        "--noconfirm",
        "--icon",
        str(icon_path),
    ]
    data_dir = ROOT / "data"
    for name in BUNDLE_DATA_FILES:
        path = data_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Build requires data file: {path}")
        cmd.extend(["--add-data", _pyinstaller_add_data(f"data/{name}")])
    manifest = data_dir / "bundle_updates.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"Build requires data file: {manifest}")
    cmd.extend(["--add-data", _pyinstaller_add_data("data/bundle_updates.json")])
    version_file = ROOT / "version.txt"
    if not version_file.is_file():
        raise FileNotFoundError(f"Build requires version file: {version_file}")
    cmd.extend(["--add-data", _pyinstaller_add_data("version.txt", dest_dir=".")])
    for asset_name in ("icon.ico", "icon.png"):
        asset_path = ASSETS_DIR / asset_name
        if asset_path.is_file():
            cmd.extend(["--add-data", _pyinstaller_add_data(f"assets/{asset_name}", dest_dir="assets")])
    cmd.append("main.py")

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
