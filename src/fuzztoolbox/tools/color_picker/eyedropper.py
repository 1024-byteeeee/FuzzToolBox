"""Full-screen eyedropper overlay for sampling a color from anywhere on screen."""

import ctypes
import os
import platform
import subprocess
import tempfile
import threading

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
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
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        win_id = widget.winId()
        ns_view = objc.objc_msgSend(win_id, ctypes.c_void_p(
            objc.sel_registerName(b"window")))
        if ns_view:
            objc.objc_msgSend.restype = None
            objc.objc_msgSend.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
            objc.objc_msgSend(ns_view, ctypes.c_void_p(
                objc.sel_registerName(b"setLevel:")), 26)
    except Exception:
        pass


def _grab_screen(screen) -> QPixmap:
    """Capture a single screen. Uses screencapture on macOS, Qt fallback elsewhere."""
    if platform.system() != "Darwin":
        return screen.grabWindow(0)

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
                return pixmap
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return screen.grabWindow(0)


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

        # Capture screens in a background thread
        def _do_capture():
            shots = []
            for screen in screens:
                pixmap = _grab_screen(screen)
                shots.append((screen.geometry(), pixmap))
            self._screens_ready.emit(shots)

        threading.Thread(target=_do_capture, daemon=True).start()

    def _show_overlay(self, shots: list) -> None:
        """Called on the main thread via signal to display the overlay."""
        self._screen_shots = shots
        self._active = True
        self.setGeometry(self._virtual)
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

        pos = self._cursor_pos

        # Find the screen containing the cursor for the magnifier.
        ratio = 1.0
        for geom, pixmap in self._screen_shots:
            if geom.contains(pos):
                ratio = pixmap.devicePixelRatio()
                break

        sample = QRect(
            int((pos.x() - self.SAMPLE_RADIUS) * ratio),
            int((pos.y() - self.SAMPLE_RADIUS) * ratio),
            int(self.SAMPLE_RADIUS * 2 * ratio),
            int(self.SAMPLE_RADIUS * 2 * ratio),
        )

        # Use the primary screen pixmap for sampling colour.
        primary_pixmap = self._screen_shots[0][1] if self._screen_shots else QPixmap()
        cropped = primary_pixmap.copy(sample)

        preview_rect = QRect(
            pos.x() + 18,
            pos.y() + 18,
            self.PREVIEW_SIZE,
            self.PREVIEW_SIZE,
        )
        if preview_rect.right() > self.width():
            preview_rect.moveRight(pos.x() - 18)
        if preview_rect.bottom() > self.height():
            preview_rect.moveBottom(pos.y() - 18)

        painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(preview_rect).adjusted(-1, -1, 1, 1), 8, 8)
        painter.drawPixmap(preview_rect, cropped)

        color = self._color_at(pos)
        hex_value = color.name().upper()
        label_rect = QRect(
            preview_rect.left(),
            preview_rect.bottom() + 8,
            self.PREVIEW_SIZE,
            24,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRoundedRect(QRectF(label_rect), 6, 6)
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(label_rect, Qt.AlignCenter, hex_value)

        # Crosshair.
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        painter.drawLine(pos.x() - 10, pos.y(), pos.x() + 10, pos.y())
        painter.drawLine(pos.x(), pos.y() - 10, pos.x(), pos.y() + 10)

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
                return QColor(image.pixel(x, y))
        return QColor(0, 0, 0)

    def mouseMoveEvent(self, event):
        self._cursor_pos = event.position().toPoint()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            color = self._color_at(event.position().toPoint())
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
