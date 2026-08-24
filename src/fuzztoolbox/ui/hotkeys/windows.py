"""Windows global-hotkey adapter and shortcut recorder."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

from .parser import windows_key_code


def windows_key_name(virtual_key: int) -> str:
    """Translate left/right Windows key variants into a portable name."""
    virtual_key = {
        0xA0: 0x10,
        0xA1: 0x10,
        0xA2: 0x11,
        0xA3: 0x11,
        0xA4: 0x12,
        0xA5: 0x12,
        0x5C: 0x5B,
    }.get(virtual_key, virtual_key)
    if 0x41 <= virtual_key <= 0x5A or 0x30 <= virtual_key <= 0x39:
        return chr(virtual_key)
    if 0x70 <= virtual_key <= 0x87:
        return f"F{virtual_key - 0x6F}"
    return {
        0x08: "Backspace",
        0x09: "Tab",
        0x0D: "Enter",
        0x10: "Shift",
        0x11: "Ctrl",
        0x12: "Alt",
        0x1B: "Escape",
        0x20: "Space",
        0x25: "Left",
        0x26: "Up",
        0x27: "Right",
        0x28: "Down",
        0x2E: "Delete",
        0x5B: "Meta",
        0xBB: "=",
        0xBD: "-",
        0xBC: ",",
        0xBE: ".",
        0xBF: "/",
        0xC0: "`",
        0xDB: "[",
        0xDC: "\\",
        0xDD: "]",
        0xDE: "'",
    }.get(virtual_key, "")


class WindowsShortcutRecorder(QObject):
    """Capture and suppress keys while a shortcut editor has focus on Windows."""

    key_changed = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hook = None
        self._callback = None

    @property
    def active(self) -> bool:
        return bool(self._hook)

    def start(self) -> bool:
        if sys.platform != "win32" or self._hook:
            return bool(self._hook)

        class KeyboardData(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        def callback(code, message, data):
            if code >= 0 and message in (0x0100, 0x0101, 0x0104, 0x0105):
                key_code = ctypes.cast(
                    data, ctypes.POINTER(KeyboardData)
                ).contents.vkCode
                key = windows_key_name(key_code)
                if key:
                    self.key_changed.emit(key, message in (0x0100, 0x0104))
                    # Suppress captured keys, including the Windows key, so they
                    # do not leak into the shell or another application.
                    return 1
            return ctypes.windll.user32.CallNextHookEx(
                self._hook, code, message, data
            )

        user32 = ctypes.windll.user32
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            callback_type,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._callback = callback_type(callback)
        kernel32 = ctypes.windll.kernel32
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._hook = user32.SetWindowsHookExW(
            13, self._callback, kernel32.GetModuleHandleW(None), 0
        )
        if not self._hook:
            self._callback = None
            return False
        return True

    def stop(self) -> None:
        if self._hook:
            ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        self._callback = None


class _WindowsHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback: Callable[[], None], hotkey_id: int):
        super().__init__()
        self.callback = callback
        self.hotkey_id = hotkey_id

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and int(msg.wParam) == self.hotkey_id:
                self.callback()
                return True, 0
        return False, 0


class WindowsHotkeyAdapter:
    """Own all Windows registration and hook resources for one shortcut."""

    def __init__(
        self,
        app,
        hotkey_id: int,
        activated: Callable[[], None],
        update_chord: Callable[[set[int], int, bool], None],
    ):
        self._app = app
        self._activated = activated
        self._update_chord = update_chord
        self._native_id = 0x4659 + hotkey_id
        self._filter = None
        self._hook = None
        self._hook_callback = None

    def register_simple(self, modifiers: set[str], key: str) -> bool:
        virtual_key = windows_key_code(key)
        if virtual_key is None:
            return False
        native_modifiers = 0x4000
        modifier_map = {
            "alt": 0x0001,
            "ctrl": 0x0002,
            "control": 0x0002,
            "shift": 0x0004,
            "meta": 0x0008,
            "win": 0x0008,
        }
        for modifier in modifiers:
            value = modifier_map.get(modifier)
            if value is None:
                return False
            native_modifiers |= value
        if not ctypes.windll.user32.RegisterHotKey(
            None, self._native_id, native_modifiers, virtual_key
        ):
            return False
        self._filter = _WindowsHotkeyFilter(self._activated, self._native_id)
        self._app.installNativeEventFilter(self._filter)
        return True

    def register_chord(self, parts: list[str]) -> bool:
        expected_codes = {windows_key_code(part) for part in parts}
        if None in expected_codes or len(expected_codes) != len(set(parts)):
            return False
        expected_codes.discard(None)

        class KeyboardData(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        def callback(code, message, data):
            if code >= 0 and message in (0x0100, 0x0101, 0x0104, 0x0105):
                key = ctypes.cast(data, ctypes.POINTER(KeyboardData)).contents.vkCode
                key = {
                    0xA0: 0x10,
                    0xA1: 0x10,
                    0xA2: 0x11,
                    0xA3: 0x11,
                    0xA4: 0x12,
                    0xA5: 0x12,
                    0x5C: 0x5B,
                }.get(key, key)
                self._update_chord(
                    expected_codes, key, message in (0x0100, 0x0104)
                )
            return ctypes.windll.user32.CallNextHookEx(
                self._hook, code, message, data
            )

        self._hook_callback = callback_type(callback)
        user32 = ctypes.windll.user32
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            callback_type,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32 = ctypes.windll.kernel32
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._hook = user32.SetWindowsHookExW(
            13,
            self._hook_callback,
            kernel32.GetModuleHandleW(None),
            0,
        )
        if not self._hook:
            self._hook_callback = None
            return False
        return True

    def unregister(self) -> None:
        if self._filter is not None:
            ctypes.windll.user32.UnregisterHotKey(None, self._native_id)
            self._app.removeNativeEventFilter(self._filter)
            self._filter = None
        if self._hook:
            ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        self._hook_callback = None
