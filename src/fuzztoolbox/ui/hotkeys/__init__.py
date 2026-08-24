"""Internal global-hotkey implementation.

Callers should import the stable compatibility interface from
``fuzztoolbox.ui.global_hotkey``.  This package keeps parsing, lifecycle, and
native platform details behind that seam.
"""

from .manager import GlobalHotkeyManager
from .parser import (
    canonical_shortcut,
    windows_shortcut_needs_registration_probe,
    windows_shortcut_supported,
)
from .windows import WindowsShortcutRecorder

__all__ = [
    "GlobalHotkeyManager",
    "WindowsShortcutRecorder",
    "canonical_shortcut",
    "windows_shortcut_needs_registration_probe",
    "windows_shortcut_supported",
]
