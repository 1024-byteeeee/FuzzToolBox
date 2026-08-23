"""Enumerate visible top-level windows for screenshot region snapping."""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

from PySide6.QtCore import QRect


def enumerate_window_rects(*, include_current_process=False):
    """Return visible window rectangles in front-to-back order."""
    try:
        if sys.platform == "win32":
            return _windows_window_rects(
                include_current_process=include_current_process
            )
        if sys.platform == "darwin":
            return _macos_window_rects(
                include_current_process=include_current_process
            )
    except (AttributeError, OSError, TypeError, ValueError):
        return []
    return []


def _windows_window_rects(*, include_current_process=False):
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    own_pid = os.getpid()
    rectangles = []
    seen = set()
    desktop_classes = {"Progman", "WorkerW"}

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def append_window(hwnd, *, include_tool=False):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == own_pid and not include_current_process:
            return
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_name, len(class_name))
        if class_name.value in desktop_classes:
            return
        if not include_tool and user32.GetWindowLongW(hwnd, -20) & 0x80:
            return

        cloaked = wintypes.DWORD()
        if dwmapi.DwmGetWindowAttribute(
            hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        ) == 0 and cloaked.value:
            return

        rect = wintypes.RECT()
        if dwmapi.DwmGetWindowAttribute(
            hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
        ) != 0 and not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom

        converter = getattr(user32, "PhysicalToLogicalPointForPerMonitorDPI", None)
        if converter is not None:
            first = wintypes.POINT(left, top)
            second = wintypes.POINT(right, bottom)
            if converter(hwnd, ctypes.byref(first)) and converter(hwnd, ctypes.byref(second)):
                left, top, right, bottom = first.x, first.y, second.x, second.y

        values = (left, top, right - left, bottom - top)
        if values[2] >= 40 and values[3] >= 30 and values not in seen:
            seen.add(values)
            rectangles.append(QRect(*values))

    child_callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    def append_child(hwnd, _lparam):
        append_window(hwnd, include_tool=True)
        return True

    def callback(hwnd, _lparam):
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_name, len(class_name))
        if class_name.value in {"Shell_TrayWnd", "Shell_SecondaryTrayWnd"}:
            # Insert shell children exactly where the taskbar occurs in the
            # top-level Z-order, so a fullscreen window above it still wins.
            user32.EnumChildWindows(hwnd, child_callback_type(append_child), 0)
            append_window(hwnd, include_tool=True)
        else:
            append_window(hwnd)
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return rectangles


class _CGPoint(ctypes.Structure):
    _fields_ = (("x", ctypes.c_double), ("y", ctypes.c_double))


class _CGSize(ctypes.Structure):
    _fields_ = (("width", ctypes.c_double), ("height", ctypes.c_double))


class _CGRect(ctypes.Structure):
    _fields_ = (("origin", _CGPoint), ("size", _CGSize))


def _macos_window_rects(*, include_current_process=False):
    core_graphics = ctypes.CDLL(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    core_foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    core_graphics.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    core_graphics.CGWindowListCopyWindowInfo.argtypes = (ctypes.c_uint32, ctypes.c_uint32)
    core_graphics.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
    core_graphics.CGRectMakeWithDictionaryRepresentation.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_CGRect),
    )
    core_foundation.CFArrayGetCount.restype = ctypes.c_long
    core_foundation.CFArrayGetCount.argtypes = (ctypes.c_void_p,)
    core_foundation.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    core_foundation.CFArrayGetValueAtIndex.argtypes = (ctypes.c_void_p, ctypes.c_long)
    core_foundation.CFDictionaryGetValue.restype = ctypes.c_void_p
    core_foundation.CFDictionaryGetValue.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    core_foundation.CFNumberGetValue.restype = ctypes.c_bool
    core_foundation.CFNumberGetValue.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
    )
    core_foundation.CFStringCreateWithCString.restype = ctypes.c_void_p
    core_foundation.CFStringCreateWithCString.argtypes = (
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_uint32,
    )
    core_foundation.CFRelease.argtypes = (ctypes.c_void_p,)

    def make_key(value):
        return core_foundation.CFStringCreateWithCString(
            None, value.encode(), 0x08000100
        )

    keys = {
        name: make_key(name)
        for name in (
            "kCGWindowBounds",
            "kCGWindowLayer",
            "kCGWindowAlpha",
            "kCGWindowOwnerPID",
            "kCGWindowOwnerName",
            "kCGWindowName",
        )
    }
    window_list = core_graphics.CGWindowListCopyWindowInfo(0x11, 0)
    rectangles = []
    seen = set()
    try:
        if not window_list:
            return []
        for index in range(core_foundation.CFArrayGetCount(window_list)):
            info = core_foundation.CFArrayGetValueAtIndex(window_list, index)
            layer = _macos_number(core_foundation, info, keys["kCGWindowLayer"], integer=True)
            alpha = _macos_number(core_foundation, info, keys["kCGWindowAlpha"])
            pid = _macos_number(core_foundation, info, keys["kCGWindowOwnerPID"], integer=True)
            owner = _macos_string(
                core_foundation, info, keys["kCGWindowOwnerName"]
            )
            name = _macos_string(core_foundation, info, keys["kCGWindowName"])
            if alpha <= 0.01 or (
                pid == os.getpid() and not include_current_process
            ):
                continue
            bounds = core_foundation.CFDictionaryGetValue(
                info, keys["kCGWindowBounds"]
            )
            rect = _CGRect()
            if not bounds or not core_graphics.CGRectMakeWithDictionaryRepresentation(
                bounds, ctypes.byref(rect)
            ):
                continue
            values = (
                round(rect.origin.x),
                round(rect.origin.y),
                round(rect.size.width),
                round(rect.size.height),
            )
            if not _use_macos_window(owner, name, layer, values):
                continue
            if values not in seen:
                seen.add(values)
                rectangles.append(QRect(*values))
    finally:
        if window_list:
            core_foundation.CFRelease(window_list)
        for key in keys.values():
            if key:
                core_foundation.CFRelease(key)
    return rectangles


def _macos_number(core_foundation, dictionary, key, *, integer=False):
    value = core_foundation.CFDictionaryGetValue(dictionary, key)
    if not value:
        return 0
    if integer:
        result = ctypes.c_longlong()
        number_type = 4  # kCFNumberSInt64Type
    else:
        result = ctypes.c_double()
        number_type = 13  # kCFNumberDoubleType
    if not core_foundation.CFNumberGetValue(value, number_type, ctypes.byref(result)):
        return 0
    return result.value


def _macos_string(core_foundation, dictionary, key):
    value = core_foundation.CFDictionaryGetValue(dictionary, key)
    if not value:
        return ""
    core_foundation.CFStringGetLength.restype = ctypes.c_long
    core_foundation.CFStringGetLength.argtypes = (ctypes.c_void_p,)
    core_foundation.CFStringGetMaximumSizeForEncoding.restype = ctypes.c_long
    core_foundation.CFStringGetMaximumSizeForEncoding.argtypes = (
        ctypes.c_long,
        ctypes.c_uint32,
    )
    core_foundation.CFStringGetCString.restype = ctypes.c_bool
    core_foundation.CFStringGetCString.argtypes = (
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_uint32,
    )
    encoding = 0x08000100
    size = core_foundation.CFStringGetMaximumSizeForEncoding(
        core_foundation.CFStringGetLength(value), encoding
    ) + 1
    buffer = ctypes.create_string_buffer(max(1, size))
    if not core_foundation.CFStringGetCString(value, buffer, size, encoding):
        return ""
    return buffer.value.decode("utf-8", errors="replace")


def _use_macos_window(owner, name, layer, values):
    _x, y, width, height = values
    if width < 12 or height < 12 or name in {"Desktop", "Wallpaper"}:
        return False
    if layer == 0:
        return owner not in {"Dock", "Window Server"} and width >= 40 and height >= 30
    if owner == "Dock":
        return min(width, height) <= 256 and max(width, height) <= 4096
    if owner in {"Control Center", "SystemUIServer"}:
        return y <= 80 and height <= 80 and width <= 512
    if owner == "Window Server":
        return y <= 80 and height <= 80 and width <= 4096
    if owner == "Notification Center":
        return width <= 640 and height <= 1200
    return False
