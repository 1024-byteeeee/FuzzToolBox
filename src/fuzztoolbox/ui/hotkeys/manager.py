"""Platform-routing global-hotkey manager."""

from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import QObject, Signal

from .macos import MacOSHotkeyAdapter
from .parser import normalize_shortcut_parts, parse_shortcut, simple_shortcut
from .windows import WindowsHotkeyAdapter


def create_platform_adapter(
    platform: str,
    app,
    hotkey_id: int,
    activated: Callable[[], None],
    update_chord,
):
    """Create the one native adapter selected for this process."""
    if platform == "win32":
        return WindowsHotkeyAdapter(app, hotkey_id, activated, update_chord)
    if platform == "darwin":
        return MacOSHotkeyAdapter(hotkey_id, activated, update_chord)
    return None


class GlobalHotkeyManager(QObject):
    """Register one global shortcut while hiding native platform lifecycles."""

    activated = Signal()

    def __init__(self, app, hotkey_id=1, parent=None):
        super().__init__(parent)
        self.app = app
        self.hotkey_id = hotkey_id
        self.sequence = ""
        self._adapter = None
        self._pressed_keys = set()
        self._chord_latched = False

    def register(self, sequence: str) -> bool:
        self.unregister()
        if not sequence:
            return True
        parts = parse_shortcut(sequence)
        if parts is None:
            return False
        parts = normalize_shortcut_parts(parts)
        if parts is None:
            return False
        adapter = create_platform_adapter(
            sys.platform,
            self.app,
            self.hotkey_id,
            self.activated.emit,
            self._update_chord,
        )
        if adapter is None:
            return False
        simple = simple_shortcut(parts)
        success = (
            adapter.register_simple(*simple)
            if simple is not None
            else adapter.register_chord(parts)
        )
        if not success:
            adapter.unregister()
            return False
        self._adapter = adapter
        self.sequence = sequence
        return True

    def unregister(self) -> None:
        if self._adapter is not None:
            self._adapter.unregister()
            self._adapter = None
        self._pressed_keys.clear()
        self._chord_latched = False
        self.sequence = ""

    def _update_chord(self, expected, key, pressed) -> None:
        if pressed:
            self._pressed_keys.add(key)
        else:
            self._pressed_keys.discard(key)
        matched = expected == self._pressed_keys
        if matched and not self._chord_latched:
            self._chord_latched = True
            self.activated.emit()
        elif not matched:
            self._chord_latched = False
