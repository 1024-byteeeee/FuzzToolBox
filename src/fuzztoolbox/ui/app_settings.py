"""Shared application settings with a visible, upgrade-safe data location."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from PySide6.QtCore import QSettings


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        for parent in executable.parents:
            if parent.name.endswith(".app"):
                return parent
        return executable.parent
    return Path(__file__).resolve().parents[3]


def create_settings() -> QSettings:
    root = application_root()
    if platform.system() == "Darwin":
        # Keep preferences outside the .app bundle so replacing the app does
        # not erase shortcuts. Documents is visible and easy to back up.
        root = Path.home() / "Documents" / "FuzzToolBox"
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    settings_path = data_dir / "FuzzToolBox.ini"
    app_root = application_root()
    legacy_paths = (
        app_root / "data" / "FuzzToolBox.ini",
        app_root / "FuzzToolBox.ini",
    )
    if not settings_path.exists():
        for legacy_path in legacy_paths:
            if legacy_path.is_file():
                try:
                    legacy_path.replace(settings_path)
                except OSError:
                    pass
                break
    return QSettings(str(settings_path), QSettings.IniFormat)
