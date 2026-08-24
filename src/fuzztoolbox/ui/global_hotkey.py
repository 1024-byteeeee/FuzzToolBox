"""Stable compatibility interface for native global hotkeys.

Platform-specific resource management lives in :mod:`fuzztoolbox.ui.hotkeys`.
Keeping this module as the import seam avoids exposing native implementation
details to the main window and settings UI.
"""

from .hotkeys import (
    GlobalHotkeyManager,
    WindowsShortcutRecorder,
    canonical_shortcut,
    windows_shortcut_needs_registration_probe,
    windows_shortcut_supported,
)
from .hotkeys import macos as _macos

_MacEventHotKeyID = _macos.MacEventHotKeyID
_macos_event_hotkey_id = _macos.macos_event_hotkey_id
_macos_event_matches = _macos.macos_event_matches

__all__ = [
    "GlobalHotkeyManager",
    "WindowsShortcutRecorder",
    # Retained for the existing native-dispatcher tests and downstream users
    # that imported these historical implementation helpers directly.
    "_MacEventHotKeyID",
    "_macos_event_hotkey_id",
    "_macos_event_matches",
    "canonical_shortcut",
    "windows_shortcut_needs_registration_probe",
    "windows_shortcut_supported",
]
