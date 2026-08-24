"""macOS Carbon and event-tap global-hotkey adapter."""

from __future__ import annotations

import ctypes
import ctypes.util
from typing import Callable


class MacEventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


class _MacEventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


def fourcc(value: str) -> int:
    return int.from_bytes(value.encode("ascii"), "big")


def macos_event_hotkey_id(carbon, event) -> int | None:
    """Read FuzzToolBox's registered Carbon hotkey id from an event."""
    event_hotkey = MacEventHotKeyID()
    actual_size = ctypes.c_uint32()
    status = carbon.GetEventParameter(
        event,
        0x2D2D2D2D,
        0x686B6964,
        None,
        ctypes.sizeof(event_hotkey),
        ctypes.byref(actual_size),
        ctypes.byref(event_hotkey),
    )
    if status != 0 or event_hotkey.signature != fourcc("FZTB"):
        return None
    return int(event_hotkey.id)


def macos_event_matches(carbon, event, hotkey_id: int) -> bool:
    """Return whether a Carbon event belongs to the requested hotkey id."""
    return macos_event_hotkey_id(carbon, event) == hotkey_id


# All Carbon registrations reach one application event target. A process-wide
# dispatcher prevents stale per-shortcut handlers from swallowing events.
_HOTKEY_CALLBACKS: dict[int, Callable[[], None]] = {}
_EVENT_CARBON = None
_EVENT_HANDLER = ctypes.c_void_p()
_EVENT_CALLBACK = None

_CG_EVENT_KEY_DOWN = 10
_CG_EVENT_KEY_UP = 11
_CG_EVENT_FLAGS_CHANGED = 12
_MAC_MODIFIER_EVENT_MASKS = {
    # Qt's portable Ctrl maps to Command and Meta maps to Control on macOS.
    0x37: 1 << 20,
    0x36: 1 << 20,
    0x38: 1 << 17,
    0x3C: 1 << 17,
    0x3A: 1 << 19,
    0x3D: 1 << 19,
    0x3B: 1 << 18,
    0x3E: 1 << 18,
}


def _load_event_tap_libraries():
    """Load the two frameworks used by a multi-key event tap."""
    return (
        ctypes.CDLL(ctypes.util.find_library("ApplicationServices")),
        ctypes.CDLL(ctypes.util.find_library("CoreFoundation")),
    )


def _run_loop_common_modes(core_foundation):
    """Return CoreFoundation's shared common-mode run-loop value."""
    return ctypes.c_void_p.in_dll(core_foundation, "kCFRunLoopCommonModes")


def _event_key_pressed(core_graphics, event_type: int, event, key_code: int) -> bool:
    """Translate a CoreGraphics keyboard event into a pressed state."""
    if event_type == _CG_EVENT_KEY_DOWN:
        return True
    if event_type == _CG_EVENT_KEY_UP:
        return False
    if event_type == _CG_EVENT_FLAGS_CHANGED:
        native_mask = _MAC_MODIFIER_EVENT_MASKS.get(key_code, 0)
        return bool(native_mask and core_graphics.CGEventGetFlags(event) & native_mask)
    return False


def _hotkey_dispatcher():
    global _EVENT_CALLBACK, _EVENT_CARBON, _EVENT_HANDLER
    if _EVENT_CARBON is not None and _EVENT_HANDLER.value:
        return _EVENT_CARBON

    carbon = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/Carbon.framework/Carbon"
    )
    carbon.GetEventParameter.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    carbon.GetEventParameter.restype = ctypes.c_int32
    callback_type = ctypes.CFUNCTYPE(
        ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    )

    def callback(_next, event, _data):
        activation = _HOTKEY_CALLBACKS.get(macos_event_hotkey_id(carbon, event))
        if activation is not None:
            activation()
        return 0

    carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
    carbon.InstallEventHandler.argtypes = [
        ctypes.c_void_p,
        callback_type,
        ctypes.c_uint32,
        ctypes.POINTER(_MacEventTypeSpec),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    carbon.InstallEventHandler.restype = ctypes.c_int32
    event_type = _MacEventTypeSpec(fourcc("keyb"), 6)
    callback_ref = callback_type(callback)
    handler = ctypes.c_void_p()
    status = carbon.InstallEventHandler(
        carbon.GetApplicationEventTarget(),
        callback_ref,
        1,
        ctypes.byref(event_type),
        None,
        ctypes.byref(handler),
    )
    if status != 0:
        return None
    _EVENT_CARBON = carbon
    _EVENT_HANDLER = handler
    _EVENT_CALLBACK = callback_ref
    return carbon


class MacOSHotkeyAdapter:
    """Own all Carbon/event-tap resources for one shortcut."""

    def __init__(
        self,
        hotkey_id: int,
        activated: Callable[[], None],
        update_chord: Callable[[set[str], str, bool], None],
    ):
        self._hotkey_id = hotkey_id
        self._activated = activated
        self._update_chord = update_chord
        self._hotkey_ref = ctypes.c_void_p()
        self._tap = ctypes.c_void_p()
        self._source = ctypes.c_void_p()
        self._callback = None

    def register_simple(self, modifiers: set[str], key: str) -> bool:
        key_code = MAC_KEY_CODES.get(key)
        if key_code is None:
            return False
        modifier_map = {
            "ctrl": 1 << 8,
            "cmd": 1 << 8,
            "command": 1 << 8,
            "shift": 1 << 9,
            "alt": 1 << 11,
            "option": 1 << 11,
            "meta": 1 << 12,
            "control": 1 << 12,
        }
        native_modifiers = 0
        for modifier in modifiers:
            value = modifier_map.get(modifier)
            if value is None:
                return False
            native_modifiers |= value

        carbon = _hotkey_dispatcher()
        if carbon is None:
            return False
        carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            MacEventHotKeyID,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.RegisterEventHotKey.restype = ctypes.c_int32
        target = carbon.GetApplicationEventTarget()
        hotkey_id = MacEventHotKeyID(fourcc("FZTB"), self._hotkey_id)
        status = carbon.RegisterEventHotKey(
            key_code,
            native_modifiers,
            hotkey_id,
            target,
            0,
            ctypes.byref(self._hotkey_ref),
        )
        if status != 0:
            return False
        _HOTKEY_CALLBACKS[self._hotkey_id] = self._activated
        return True

    def register_chord(self, parts: list[str]) -> bool:
        expected_keys = set(parts)
        if any(part not in MAC_KEY_CODES for part in expected_keys):
            return False
        core_graphics, core_foundation = _load_event_tap_libraries()
        core_graphics.CGEventGetIntegerValueField.restype = ctypes.c_int64
        core_graphics.CGEventGetIntegerValueField.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        core_graphics.CGEventGetFlags.restype = ctypes.c_uint64
        core_graphics.CGEventGetFlags.argtypes = [ctypes.c_void_p]
        callback_type = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )

        def callback(_proxy, event_type, event, _context):
            if event_type in (0xFFFFFFFE, 0xFFFFFFFF):
                core_graphics.CGEventTapEnable(self._tap, True)
                return event
            key_code = int(core_graphics.CGEventGetIntegerValueField(event, 9))
            key = MAC_EVENT_KEYS.get(key_code)
            if key is not None:
                self._update_chord(
                    expected_keys,
                    key,
                    _event_key_pressed(core_graphics, event_type, event, key_code),
                )
            return event

        self._callback = callback_type(callback)
        mask = (1 << 10) | (1 << 11) | (1 << 12)
        core_graphics.CGEventTapCreate.restype = ctypes.c_void_p
        core_graphics.CGEventTapCreate.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint64,
            callback_type,
            ctypes.c_void_p,
        ]
        tap = core_graphics.CGEventTapCreate(1, 0, 1, mask, self._callback, None)
        if not tap:
            self._callback = None
            return False
        self._tap = ctypes.c_void_p(tap)
        core_foundation.CFMachPortCreateRunLoopSource.restype = ctypes.c_void_p
        core_foundation.CFMachPortCreateRunLoopSource.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_long,
        ]
        core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        source = core_foundation.CFMachPortCreateRunLoopSource(None, tap, 0)
        if not source:
            core_foundation.CFRelease(tap)
            self._tap = ctypes.c_void_p()
            self._callback = None
            return False
        self._source = ctypes.c_void_p(source)
        core_foundation.CFRunLoopGetMain.restype = ctypes.c_void_p
        core_foundation.CFRunLoopAddSource.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        run_loop = core_foundation.CFRunLoopGetMain()
        common_modes = _run_loop_common_modes(core_foundation)
        core_foundation.CFRunLoopAddSource(run_loop, source, common_modes)
        core_graphics.CGEventTapEnable.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        core_graphics.CGEventTapEnable(tap, True)
        return True

    def unregister(self) -> None:
        if self._hotkey_ref.value:
            carbon = _EVENT_CARBON or ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/Carbon.framework/Carbon"
            )
            carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
            carbon.UnregisterEventHotKey.restype = ctypes.c_int32
            carbon.UnregisterEventHotKey(self._hotkey_ref)
            if _HOTKEY_CALLBACKS.get(self._hotkey_id) is self._activated:
                _HOTKEY_CALLBACKS.pop(self._hotkey_id, None)
            self._hotkey_ref = ctypes.c_void_p()

        if self._source.value:
            _core_graphics, core_foundation = _load_event_tap_libraries()
            core_foundation.CFRunLoopGetMain.restype = ctypes.c_void_p
            core_foundation.CFRunLoopRemoveSource.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            core_foundation.CFMachPortInvalidate.argtypes = [ctypes.c_void_p]
            core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
            run_loop = core_foundation.CFRunLoopGetMain()
            common_modes = _run_loop_common_modes(core_foundation)
            core_foundation.CFRunLoopRemoveSource(
                run_loop, self._source, common_modes
            )
            if self._tap.value:
                core_foundation.CFMachPortInvalidate(self._tap)
                core_foundation.CFRelease(self._tap)
            core_foundation.CFRelease(self._source)
            self._source = ctypes.c_void_p()
            self._tap = ctypes.c_void_p()
            self._callback = None


MAC_KEY_CODES = {
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

MAC_EVENT_KEYS = {code: key for key, code in MAC_KEY_CODES.items()}
MAC_EVENT_KEYS.update({
    0x37: "ctrl", 0x36: "ctrl", 0x38: "shift", 0x3C: "shift",
    0x3A: "alt", 0x3D: "alt", 0x3B: "meta", 0x3E: "meta",
})
