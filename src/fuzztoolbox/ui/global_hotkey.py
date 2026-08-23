"""Native global hotkey registration for Windows and macOS."""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


def _parse_shortcut(sequence: str):
    parts = [part.strip().lower() for part in sequence.split("+") if part.strip()]
    if len(parts) < 2:
        return None
    return parts


_MODIFIER_NAMES = {
    "alt", "option", "ctrl", "control", "shift", "meta", "cmd", "command", "win"
}


def _simple_shortcut(parts):
    if parts[-1] in _MODIFIER_NAMES or any(
        part not in _MODIFIER_NAMES for part in parts[:-1]
    ):
        return None
    return set(parts[:-1]), parts[-1]


def _windows_key_code(key: str):
    if len(key) == 1 and key.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        return 0x6F + int(key[1:])
    return {
        "backspace": 0x08, "tab": 0x09, "return": 0x0D, "enter": 0x0D,
        "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
        "option": 0x12, "escape": 0x1B, "esc": 0x1B, "space": 0x20,
        "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "meta": 0x5B, "win": 0x5B, "cmd": 0x5B, "command": 0x5B,
        "plus": 0xBB, "=": 0xBB, "-": 0xBD, ",": 0xBC, ".": 0xBE,
        "/": 0xBF, "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD,
        "'": 0xDE,
    }.get(key)


class _WindowsHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback, hotkey_id):
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


class GlobalHotkeyManager(QObject):
    activated = Signal()

    def __init__(self, app, hotkey_id=1, parent=None):
        super().__init__(parent)
        self.app = app
        self.hotkey_id = hotkey_id
        self.sequence = ""
        self._windows_filter = None
        self._windows_hook = None
        self._windows_hook_callback = None
        self._windows_id = 0x4659 + hotkey_id
        self._mac_ref = ctypes.c_void_p()
        self._mac_tap = ctypes.c_void_p()
        self._mac_handler = ctypes.c_void_p()
        self._mac_callback = None
        self._mac_source = ctypes.c_void_p()
        self._pressed_keys = set()
        self._chord_latched = False

    def register(self, sequence: str) -> bool:
        self.unregister()
        if not sequence:
            return True
        parts = _parse_shortcut(sequence)
        if parts is None:
            return False
        simple = _simple_shortcut(parts)
        if sys.platform == "win32" and simple is not None:
            success = self._register_windows(*simple)
        elif sys.platform == "darwin" and simple is not None:
            success = self._register_macos(*simple)
        elif sys.platform == "win32":
            success = self._register_windows_chord(parts)
        elif sys.platform == "darwin":
            success = self._register_macos_chord(parts)
        else:
            success = False
        if success:
            self.sequence = sequence
        return success

    def unregister(self):
        if sys.platform == "win32" and self._windows_filter is not None:
            ctypes.windll.user32.UnregisterHotKey(None, self._windows_id)
            self.app.removeNativeEventFilter(self._windows_filter)
            self._windows_filter = None
        if sys.platform == "win32" and self._windows_hook:
            ctypes.windll.user32.UnhookWindowsHookEx(self._windows_hook)
            self._windows_hook = None
            self._windows_hook_callback = None
        elif sys.platform == "darwin" and (
            self._mac_ref.value or self._mac_handler.value
        ):
            carbon = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/Carbon.framework/Carbon"
            )
            if self._mac_ref.value:
                carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
                carbon.UnregisterEventHotKey.restype = ctypes.c_int32
                carbon.UnregisterEventHotKey(self._mac_ref)
            if self._mac_handler.value:
                carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]
                carbon.RemoveEventHandler.restype = ctypes.c_int32
                carbon.RemoveEventHandler(self._mac_handler)
                self._mac_handler = ctypes.c_void_p()
            self._mac_ref = ctypes.c_void_p()
        if sys.platform == "darwin" and self._mac_source.value:
            core_foundation = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
            core_foundation.CFRunLoopGetMain.restype = ctypes.c_void_p
            core_foundation.CFRunLoopRemoveSource.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            ]
            core_foundation.CFMachPortInvalidate.argtypes = [ctypes.c_void_p]
            core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
            run_loop = core_foundation.CFRunLoopGetMain()
            common_modes = ctypes.c_void_p.in_dll(
                core_foundation, "kCFRunLoopCommonModes"
            )
            core_foundation.CFRunLoopRemoveSource(
                run_loop, self._mac_source, common_modes
            )
            if self._mac_tap.value:
                core_foundation.CFMachPortInvalidate(self._mac_tap)
                core_foundation.CFRelease(self._mac_tap)
            core_foundation.CFRelease(self._mac_source)
            self._mac_source = ctypes.c_void_p()
            self._mac_tap = ctypes.c_void_p()
            self._mac_callback = None
        self._pressed_keys.clear()
        self._chord_latched = False
        self.sequence = ""

    def _update_chord(self, expected, key, pressed):
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

    def _register_windows_chord(self, parts):
        expected_codes = {_windows_key_code(part) for part in parts}
        if None in expected_codes or len(expected_codes) != len(set(parts)):
            return False
        expected_codes.discard(None)

        class KeyboardData(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        def callback(code, message, data):
            if code >= 0 and message in (0x0100, 0x0101, 0x0104, 0x0105):
                key = ctypes.cast(data, ctypes.POINTER(KeyboardData)).contents.vkCode
                key = {
                    0xA0: 0x10, 0xA1: 0x10, 0xA2: 0x11, 0xA3: 0x11,
                    0xA4: 0x12, 0xA5: 0x12, 0x5C: 0x5B,
                }.get(key, key)
                self._update_chord(expected_codes, key, message in (0x0100, 0x0104))
            return ctypes.windll.user32.CallNextHookEx(
                self._windows_hook, code, message, data
            )

        self._windows_hook_callback = callback_type(callback)
        self._windows_hook = ctypes.windll.user32.SetWindowsHookExW(
            13,
            self._windows_hook_callback,
            ctypes.windll.kernel32.GetModuleHandleW(None),
            0,
        )
        return bool(self._windows_hook)

    def _register_macos_chord(self, parts):
        expected_keys = set(parts)
        if any(part not in _MAC_KEY_CODES for part in expected_keys):
            return False
        core_graphics = ctypes.CDLL(ctypes.util.find_library("ApplicationServices"))
        core_foundation = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
        core_graphics.CGEventGetIntegerValueField.restype = ctypes.c_int64
        core_graphics.CGEventGetIntegerValueField.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32
        ]
        callback_type = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )

        def callback(_proxy, event_type, event, _context):
            if event_type in (0xFFFFFFFE, 0xFFFFFFFF):
                core_graphics.CGEventTapEnable(self._mac_tap, True)
                return event
            key_code = int(core_graphics.CGEventGetIntegerValueField(event, 9))
            key = _MAC_EVENT_KEYS.get(key_code)
            if key is not None:
                self._update_chord(expected_keys, key, event_type != 11)
            return event

        self._mac_callback = callback_type(callback)
        mask = (1 << 10) | (1 << 11) | (1 << 12)
        core_graphics.CGEventTapCreate.restype = ctypes.c_void_p
        core_graphics.CGEventTapCreate.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint64,
            callback_type, ctypes.c_void_p,
        ]
        tap = core_graphics.CGEventTapCreate(
            1, 0, 1, mask, self._mac_callback, None
        )
        if not tap:
            self._mac_callback = None
            return False
        self._mac_tap = ctypes.c_void_p(tap)
        core_foundation.CFMachPortCreateRunLoopSource.restype = ctypes.c_void_p
        core_foundation.CFMachPortCreateRunLoopSource.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long
        ]
        source = core_foundation.CFMachPortCreateRunLoopSource(None, tap, 0)
        if not source:
            core_foundation.CFRelease(tap)
            self._mac_tap = ctypes.c_void_p()
            self._mac_callback = None
            return False
        self._mac_source = ctypes.c_void_p(source)
        core_foundation.CFRunLoopGetMain.restype = ctypes.c_void_p
        core_foundation.CFRunLoopAddSource.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        ]
        run_loop = core_foundation.CFRunLoopGetMain()
        common_modes = ctypes.c_void_p.in_dll(
            core_foundation, "kCFRunLoopCommonModes"
        )
        core_foundation.CFRunLoopAddSource(run_loop, source, common_modes)
        core_graphics.CGEventTapEnable.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        core_graphics.CGEventTapEnable(tap, True)
        return True

    def _register_windows(self, modifiers, key):
        virtual_key = _windows_key_code(key)
        if virtual_key is None:
            return False
        native_modifiers = 0x4000
        modifier_map = {"alt": 0x0001, "ctrl": 0x0002, "control": 0x0002,
                        "shift": 0x0004, "meta": 0x0008, "win": 0x0008}
        for modifier in modifiers:
            value = modifier_map.get(modifier)
            if value is None:
                return False
            native_modifiers |= value
        if not ctypes.windll.user32.RegisterHotKey(
            None, self._windows_id, native_modifiers, virtual_key
        ):
            return False
        self._windows_filter = _WindowsHotkeyFilter(self.activated.emit, self._windows_id)
        self.app.installNativeEventFilter(self._windows_filter)
        return True

    def _register_macos(self, modifiers, key):
        key_code = _MAC_KEY_CODES.get(key)
        if key_code is None:
            return False
        modifier_map = {"ctrl": 1 << 8, "cmd": 1 << 8, "command": 1 << 8,
                        "shift": 1 << 9, "alt": 1 << 11, "option": 1 << 11,
                        "meta": 1 << 12, "control": 1 << 12}
        native_modifiers = 0
        for modifier in modifiers:
            value = modifier_map.get(modifier)
            if value is None:
                return False
            native_modifiers |= value

        carbon = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/Carbon.framework/Carbon"
        )

        class EventTypeSpec(ctypes.Structure):
            _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]

        class EventHotKeyID(ctypes.Structure):
            _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]

        callback_type = ctypes.CFUNCTYPE(
            ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )

        def callback(_next, _event, _data):
            self.activated.emit()
            return 0

        self._mac_callback = callback_type(callback)
        carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p,
            callback_type,
            ctypes.c_uint32,
            ctypes.POINTER(EventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.InstallEventHandler.restype = ctypes.c_int32
        carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            EventHotKeyID,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.RegisterEventHotKey.restype = ctypes.c_int32
        target = carbon.GetApplicationEventTarget()
        event_type = EventTypeSpec(_fourcc("keyb"), 6)
        handler_status = carbon.InstallEventHandler(
            target,
            self._mac_callback,
            1,
            ctypes.byref(event_type),
            None,
            ctypes.byref(self._mac_handler),
        )
        if handler_status != 0:
            return False
        hotkey_id = EventHotKeyID(_fourcc("FZTB"), self.hotkey_id)
        status = carbon.RegisterEventHotKey(
            key_code,
            native_modifiers,
            hotkey_id,
            target,
            0,
            ctypes.byref(self._mac_ref),
        )
        if status != 0 and self._mac_handler.value:
            carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]
            carbon.RemoveEventHandler.restype = ctypes.c_int32
            carbon.RemoveEventHandler(self._mac_handler)
            self._mac_handler = ctypes.c_void_p()
        return status == 0


def _fourcc(value: str) -> int:
    return int.from_bytes(value.encode("ascii"), "big")


_MAC_KEY_CODES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12,
    "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "9": 0x19,
    "7": 0x1A, "8": 0x1C, "0": 0x1D, "o": 0x1F, "u": 0x20, "i": 0x22,
    "p": 0x23, "l": 0x25, "j": 0x26, "k": 0x28, "n": 0x2D, "m": 0x2E,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60,
    "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D,
    "f11": 0x67, "f12": 0x6F,
    "return": 0x24, "enter": 0x4C, "tab": 0x30, "space": 0x31,
    "backspace": 0x33, "escape": 0x35, "esc": 0x35,
    "ctrl": 0x37, "cmd": 0x37, "command": 0x37,
    "shift": 0x38, "alt": 0x3A, "option": 0x3A,
    "meta": 0x3B, "control": 0x3B,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
    "plus": 0x18, "=": 0x18, "-": 0x1B, ",": 0x2B, ".": 0x2F,
    "/": 0x2C, "`": 0x32, "[": 0x21, "\\": 0x2A, "]": 0x1E,
    "'": 0x27,
}

_MAC_EVENT_KEYS = {code: key for key, code in _MAC_KEY_CODES.items()}
_MAC_EVENT_KEYS.update({
    0x37: "ctrl", 0x36: "ctrl",  # Command maps to Qt's Ctrl semantic
    0x38: "shift", 0x3C: "shift",
    0x3A: "alt", 0x3D: "alt",
    0x3B: "meta", 0x3E: "meta",  # Control maps to Qt's Meta semantic
})
