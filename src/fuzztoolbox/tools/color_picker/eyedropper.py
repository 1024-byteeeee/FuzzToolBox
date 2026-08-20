"""Full-screen eyedropper overlay for sampling a color from anywhere on screen."""

import ctypes
import os
import platform
import subprocess
import tempfile
import threading
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QColorSpace, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


def _raise_window_level(widget) -> None:
    """Raise the native NSWindow level above dock (20) and menu bar (24).

    kCGScreenSaverWindowLevel (26) makes the overlay cover the whole screen
    like a screenshot tool, freezing everything below it.
    """
    if platform.system() != "Darwin":
        return
    try:
        objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        win_id = widget.winId()
        ns_window = objc.objc_msgSend(
            win_id, objc.sel_registerName(b"window"))
        if ns_window:
            objc.objc_msgSend.restype = None
            objc.objc_msgSend.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
            objc.objc_msgSend(
                ns_window, objc.sel_registerName(b"setLevel:"), 26)
    except Exception:
        pass


def _ns_window(widget):
    """Return the native NSWindow pointer for a Qt widget, or None."""
    if platform.system() != "Darwin":
        return None
    try:
        objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        return objc.objc_msgSend(
            widget.winId(), objc.sel_registerName(b"window"))
    except Exception:
        return None


def native_window_is_visible(widget) -> Optional[bool]:
    """Return AppKit's visibility state, or None when unavailable."""
    ns_window = _ns_window(widget)
    if ns_window is None:
        return None
    try:
        objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.objc_msgSend.restype = ctypes.c_bool
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        return bool(objc.objc_msgSend(ns_window, objc.sel_registerName(b"isVisible")))
    except Exception:
        return None
def _set_window_opacity_no_animation(widget, opacity: float) -> None:
    """Set NSWindow.alphaValue inside a zero-duration NSAnimationContext.

    Qt's setWindowOpacity() can route through Core Animation implicit
    transitions on macOS, producing a quick fade/scale flicker.  Wrapping
    the alpha change in -[NSAnimationContext beginGrouping] with duration 0
    forces an instantaneous composite.
    """
    ns_window = _ns_window(widget)
    if ns_window is None:
        widget.setWindowOpacity(opacity)
        return
    try:
        objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        ctx_class = objc.objc_getClass(b"NSAnimationContext")
        objc.objc_msgSend(ctx_class, objc.sel_registerName(b"beginGrouping"))
        current = objc.objc_msgSend(ctx_class, objc.sel_registerName(b"currentContext"))
        objc.objc_msgSend.restype = None
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double]
        objc.objc_msgSend(current, objc.sel_registerName(b"setDuration:"), 0.0)
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double]
        objc.objc_msgSend(ns_window, objc.sel_registerName(b"setAlphaValue:"), opacity)
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        objc.objc_msgSend(ctx_class, objc.sel_registerName(b"endGrouping"))
    except Exception:
        widget.setWindowOpacity(opacity)


def hide_window_instantly(widget) -> None:
    """Remove a window from the macOS window server without animation.

    Merely setting alpha to zero leaves the NSWindow ordered and AppKit can
    re-composite it when the eyedropper overlay becomes active.  ``orderOut``
    makes the hide operation explicit while Qt can still restore the same
    widget later.
    """
    ns_window = _ns_window(widget)
    if ns_window is not None:
        try:
            objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            objc.objc_msgSend.restype = None
            objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            objc.objc_msgSend(ns_window, objc.sel_registerName(b"orderOut:"), None)
            # Keep Qt's visibility state in sync with AppKit.  This prevents
            # Qt from re-ordering the window while the compositor settles.
            widget.hide()
            return
        except Exception:
            pass
    _set_window_opacity_no_animation(widget, 0.0)
    widget.hide()


def show_window_instantly(widget) -> None:
    """Restore and activate a window without an AppKit animation."""
    ns_window = _ns_window(widget)
    if ns_window is not None:
        try:
            widget.show()
            objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            objc.objc_msgSend.restype = None
            objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            objc.objc_msgSend(ns_window, objc.sel_registerName(b"makeKeyAndOrderFront:"), None)
            widget.raise_()
            widget.activateWindow()
            return
        except Exception:
            pass
    _set_window_opacity_no_animation(widget, 1.0)
    widget.raise_()
    widget.activateWindow()


def _to_srgb_pixmap(pixmap: QPixmap) -> QPixmap:
    """Normalize a captured display image to sRGB before sampling pixels.

    Wide-gamut macOS displays commonly return Display P3 CGImages.  Reading
    those bytes as if they were sRGB makes the picker disagree with Photoshop
    and other sRGB-oriented color readouts.  Keep the source profile attached
    until Qt performs an explicit ColorSync conversion, then store the
    normalized image for both the magnifier and the final picked color.
    """
    if pixmap.isNull():
        return pixmap
    image = pixmap.toImage()
    source_space = image.colorSpace()
    if not source_space.isValid():
        return pixmap
    target_space = QColorSpace(QColorSpace.NamedColorSpace.SRgb)
    if source_space == target_space:
        return pixmap
    converted = image.convertedToColorSpace(target_space)
    if converted.isNull():
        return pixmap
    converted.setDevicePixelRatio(pixmap.devicePixelRatio())
    return QPixmap.fromImage(converted)


def _grab_screen_quartz(screen) -> QPixmap:
    """Capture a screen with CoreGraphics in-process.

    Using CGWindowListCreateImage inside the .app process binds the
    screen-recording permission to the bundle itself, so macOS asks once
    and remembers the grant.  The subprocess `screencapture` tool can be
    treated as a separate app by TCC, causing repeated prompts and, when
    permission is ambiguous, returning only the desktop wallpaper layer.
    """
    import ctypes.util

    quartz = ctypes.CDLL(ctypes.util.find_library("Quartz"))
    cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    class CGSize(ctypes.Structure):
        _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

    class CGRect(ctypes.Structure):
        _fields_ = [("origin", CGPoint), ("size", CGSize)]

    kCGWindowListOptionOnScreenOnly = 1 << 0
    kCGWindowImageDefault = 0
    kCFStringEncodingUTF8 = 0x08000100

    quartz.CGWindowListCreateImage.restype = ctypes.c_void_p
    quartz.CGWindowListCreateImage.argtypes = [
        CGRect, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    quartz.CGImageDestinationCreateWithData.restype = ctypes.c_void_p
    quartz.CGImageDestinationCreateWithData.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    quartz.CGImageDestinationAddImage.restype = None
    quartz.CGImageDestinationAddImage.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    quartz.CGImageDestinationFinalize.restype = ctypes.c_bool
    quartz.CGImageDestinationFinalize.argtypes = [ctypes.c_void_p]

    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFDataCreateMutable.restype = ctypes.c_void_p
    cf.CFDataCreateMutable.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFDataGetLength.restype = ctypes.c_long
    cf.CFDataGetLength.argtypes = [ctypes.c_void_p]
    cf.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_ubyte)
    cf.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
    cf.CFRelease.restype = None
    cf.CFRelease.argtypes = [ctypes.c_void_p]

    screen_rect = screen.geometry()
    rect = CGRect(
        CGPoint(screen_rect.x(), screen_rect.y()),
        CGSize(screen_rect.width(), screen_rect.height()),
    )
    cg_image = quartz.CGWindowListCreateImage(
        rect, kCGWindowListOptionOnScreenOnly, 0, kCGWindowImageDefault)
    if not cg_image:
        return QPixmap()

    png_data = b""
    try:
        uti = cf.CFStringCreateWithCString(None, b"public.png", kCFStringEncodingUTF8)
        if not uti:
            return QPixmap()
        try:
            data = cf.CFDataCreateMutable(None, 0)
            if not data:
                return QPixmap()
            try:
                dest = quartz.CGImageDestinationCreateWithData(data, uti, 1, None)
                if not dest:
                    return QPixmap()
                try:
                    quartz.CGImageDestinationAddImage(dest, cg_image, None)
                    if not quartz.CGImageDestinationFinalize(dest):
                        return QPixmap()
                    length = cf.CFDataGetLength(data)
                    ptr = cf.CFDataGetBytePtr(data)
                    png_data = ctypes.string_at(ptr, length)
                finally:
                    cf.CFRelease(dest)
            finally:
                cf.CFRelease(data)
        finally:
            cf.CFRelease(uti)
    finally:
        cf.CFRelease(cg_image)

    pixmap = QPixmap()
    if png_data and pixmap.loadFromData(png_data, "PNG"):
        pixmap.setDevicePixelRatio(screen.devicePixelRatio())
        return _to_srgb_pixmap(pixmap)
    return pixmap


def _grab_screen(screen) -> QPixmap:
    """Capture a single screen.

    macOS prefers in-process CoreGraphics so the screen-recording grant is
    attached to the .app bundle and all on-screen windows (including the
    Dock) are captured.  `screencapture` and Qt grabWindow remain as
    fallbacks.
    """
    if platform.system() == "Darwin":
        pixmap = _grab_screen_quartz(screen)
        if not pixmap.isNull():
            return pixmap

    if platform.system() != "Darwin":
        pixmap = screen.grabWindow(0)
        if pixmap.devicePixelRatio() != screen.devicePixelRatio():
            pixmap.setDevicePixelRatio(screen.devicePixelRatio())
        return _to_srgb_pixmap(pixmap)

    # macOS fallback: screencapture(1).
    screen_rect = screen.geometry()
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(tmp_fd)
    try:
        result = subprocess.run(
            [
                "screencapture", "-x",
                "-R", f"{screen_rect.x()},{screen_rect.y()},{screen_rect.width()},{screen_rect.height()}",
                tmp_path,
            ],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0 and os.path.exists(tmp_path):
            pixmap = QPixmap(tmp_path)
            if not pixmap.isNull():
                pixmap.setDevicePixelRatio(screen.devicePixelRatio())
                return _to_srgb_pixmap(pixmap)
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    pixmap = screen.grabWindow(0)
    if pixmap.devicePixelRatio() != screen.devicePixelRatio():
        pixmap.setDevicePixelRatio(screen.devicePixelRatio())
    return _to_srgb_pixmap(pixmap)


class EyedropperOverlay(QWidget):
    """Transparent full-screen widget that samples the pixel under the cursor."""

    color_picked = Signal(QColor)
    cancelled = Signal()
    _screens_ready = Signal(list)

    # Magnifier sample radius and display size.
    SAMPLE_RADIUS = 32
    PREVIEW_SIZE = 128

    def __init__(self, parent=None):
        super().__init__(parent)
        # Simple frameless window - let macOS handle window management
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self._screen_shots: list[tuple[QRect, QPixmap]] = []
        self._virtual = QRect()
        self._cursor_pos = QPoint()
        self._active = False
        self._screens_ready.connect(self._show_overlay)

    def begin(self) -> None:
        """Capture every screen in a background thread, then show the overlay."""
        from PySide6.QtGui import QGuiApplication

        screens = QGuiApplication.screens()
        if not screens:
            self.cancelled.emit()
            return

        self._virtual = QRect()
        for screen in screens:
            # Use geometry() to cover entire screen including dock
            self._virtual = self._virtual.united(screen.geometry())

        # QScreen.grabWindow() and QPixmap are GUI-thread-bound on Windows.
        # Calling them from a Python worker can terminate a frozen Qt process
        # in native qwindows/qimage code without raising a Python exception.
        # Keep the Windows path synchronous and short; the capture is taken
        # before the overlay is shown, so the user still sees one atomic state
        # transition and the main window remains hidden during the capture.
        if platform.system() != "Darwin":
            try:
                shots = [
                    (screen.geometry(), _grab_screen(screen))
                    for screen in screens
                ]
                self._show_overlay(shots)
            except Exception:
                import traceback
                traceback.print_exc()
                self.cancelled.emit()
            return

        # Capture screens in a background thread
        def _do_capture():
            try:
                shots = []
                for screen in screens:
                    pixmap = _grab_screen(screen)
                    shots.append((screen.geometry(), pixmap))
                self._screens_ready.emit(shots)
            except Exception:
                # Never let a background-thread exception silently swallow
                # the signal; surface it as a cancellation so the caller
                # can restore the main window and report status.
                import traceback
                traceback.print_exc()
                self.cancelled.emit()

        threading.Thread(target=_do_capture, daemon=True).start()

    def _show_overlay(self, shots: list) -> None:
        """Called on the main thread via signal to display the overlay."""
        from PySide6.QtGui import QCursor

        self._screen_shots = shots
        self._active = True
        self.setGeometry(self._virtual)
        # Seed the cursor with the current global position so the first
        # paint doesn't render the crosshair at (0, 0).
        self._cursor_pos = QCursor.pos()
        self.show()
        _raise_window_level(self)
        self.raise_()
        self.activateWindow()

    def paintEvent(self, _event):
        if not self._active:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Draw captured screens.
        for geom, pixmap in self._screen_shots:
            if not pixmap.isNull():
                painter.drawPixmap(geom.topLeft() - self._virtual.topLeft(), pixmap)

        # Semi-transparent overlay to dim the screen.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))

        # _cursor_pos stores global screen coordinates; the painter works in
        # widget coordinates, so derive both from the virtual-desktop origin.
        global_pos = self._cursor_pos
        widget_pos = global_pos - self._virtual.topLeft()

        # Find the screen containing the cursor and use *its* pixmap for
        # the magnifier crop.  Using the primary screen's pixmap here
        # produced garbage on multi-display setups.
        current_geom = None
        current_pixmap = None
        ratio = 1.0
        for geom, pixmap in self._screen_shots:
            if geom.contains(global_pos):
                current_geom = geom
                current_pixmap = pixmap
                ratio = pixmap.devicePixelRatio()
                break
        if current_pixmap is None and self._screen_shots:
            current_geom, current_pixmap = self._screen_shots[0]
            ratio = current_pixmap.devicePixelRatio()

        if current_pixmap is not None and not current_pixmap.isNull():
            local_x = global_pos.x() - current_geom.x()
            local_y = global_pos.y() - current_geom.y()
            sample = QRect(
                int((local_x - self.SAMPLE_RADIUS) * ratio),
                int((local_y - self.SAMPLE_RADIUS) * ratio),
                int(self.SAMPLE_RADIUS * 2 * ratio),
                int(self.SAMPLE_RADIUS * 2 * ratio),
            )
            cropped = current_pixmap.copy(sample)
        else:
            cropped = QPixmap()

        preview_rect = QRect(
            widget_pos.x() + 18,
            widget_pos.y() + 18,
            self.PREVIEW_SIZE,
            self.PREVIEW_SIZE,
        )
        if preview_rect.right() > self.width():
            preview_rect.moveRight(widget_pos.x() - 18)
        if preview_rect.bottom() > self.height():
            preview_rect.moveBottom(widget_pos.y() - 18)

        painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(preview_rect).adjusted(-1, -1, 1, 1), 8, 8)
        painter.drawPixmap(preview_rect, cropped)

        # Crosshair dead-centre in the magnifier so the user can see exactly
        # which pixel is being sampled.
        cx = preview_rect.center().x()
        cy = preview_rect.center().y()
        painter.setPen(QPen(QColor(0, 0, 0, 180), 2))
        painter.drawLine(cx - 12, cy, cx + 12, cy)
        painter.drawLine(cx, cy - 12, cx, cy + 12)
        painter.setPen(QPen(QColor(255, 255, 255, 235), 1))
        painter.drawLine(cx - 12, cy, cx + 12, cy)
        painter.drawLine(cx, cy - 12, cx, cy + 12)

        color = self._color_at(global_pos)
        hex_value = color.name().upper()

        # Label bar: live colour swatch + hex value.
        label_rect = QRect(
            preview_rect.left(),
            preview_rect.bottom() + 8,
            self.PREVIEW_SIZE,
            30,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRoundedRect(QRectF(label_rect), 6, 6)

        swatch_rect = QRect(
            label_rect.left() + 6,
            label_rect.top() + 5,
            20,
            20,
        )
        painter.setBrush(color)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
        painter.drawRoundedRect(QRectF(swatch_rect), 4, 4)

        text_rect = QRect(
            swatch_rect.right() + 8,
            label_rect.top(),
            label_rect.width() - swatch_rect.width() - 14,
            label_rect.height(),
        )
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, hex_value)

        # Crosshair.
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        painter.drawLine(widget_pos.x() - 10, widget_pos.y(), widget_pos.x() + 10, widget_pos.y())
        painter.drawLine(widget_pos.x(), widget_pos.y() - 10, widget_pos.x(), widget_pos.y() + 10)

    def _color_at(self, pos: QPoint) -> QColor:
        for geom, pixmap in self._screen_shots:
            if geom.contains(pos):
                if pixmap.isNull():
                    return QColor(0, 0, 0)
                ratio = pixmap.devicePixelRatio()
                local_x = pos.x() - geom.x()
                local_y = pos.y() - geom.y()
                x = min(max(int(local_x * ratio), 0), pixmap.width() - 1)
                y = min(max(int(local_y * ratio), 0), pixmap.height() - 1)
                image = pixmap.toImage()
                # pixelColor() preserves Qt's channel interpretation and
                # rounding for converted/extended-range image formats.  The
                # older QColor(image.pixel()) path unpacked the QRgb integer
                # directly and could differ from native pickers by one code
                # value on a single channel (for example ...55 vs ...54).
                return image.pixelColor(x, y)
        return QColor(0, 0, 0)

    def mouseMoveEvent(self, event):
        # Use global screen coordinates so multi-display setups with a
        # non-(0,0) virtual-desktop origin sample the correct pixel.
        self._cursor_pos = event.globalPosition().toPoint()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            color = self._color_at(event.globalPosition().toPoint())
            self._active = False
            self.hide()
            self.color_picked.emit(color)
            event.accept()
        elif event.button() == Qt.RightButton:
            self._cancel()
            event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def _cancel(self):
        self._active = False
        self.hide()
        self.cancelled.emit()
