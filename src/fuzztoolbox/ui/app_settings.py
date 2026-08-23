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
    return QSettings(str(application_root() / "FuzzToolBox.ini"), QSettings.IniFormat)
