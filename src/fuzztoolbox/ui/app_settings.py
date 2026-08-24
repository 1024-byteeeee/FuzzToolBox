"""Shared application settings stored beside the application."""

from __future__ import annotations

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
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    settings_path = data_dir / "FuzzToolBox.ini"
    legacy_path = root / "FuzzToolBox.ini"
    if legacy_path.is_file() and not settings_path.exists():
        try:
            legacy_path.replace(settings_path)
        except OSError:
            pass
    return QSettings(str(settings_path), QSettings.IniFormat)
