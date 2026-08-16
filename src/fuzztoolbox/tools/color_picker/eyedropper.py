"""Full-screen eyedropper overlay for sampling a color from anywhere on screen."""

import platform
import ctypes
import ctypes.util

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMessageBox, QWidget


def _has_screen_capture_access() -> bool:
    """Check macOS screen capture permission (10.15.4+)."""
    if platform.system() != "Darwin":
        return True
    try:
        lib = ctypes.CDLL(ctypes.util.find_library("ApplicationServices"))
        func = lib.CGPreflightScreenCaptureAccess
        func.restype = ctypes.c_bool
        return func()
    except Exception:
        return True


def _request_screen_capture_access() -> bool:
    """Request macOS screen capture permission (10.15.4+)."""
    if platform.system() != "Darwin":
        return True
    try:
        lib = ctypes.CDLL(ctypes.util.find_library("ApplicationServices"))
        func = lib.CGRequestScreenCaptureAccess
        func.restype = ctypes.c_bool
        return func()
    except Exception:
        return True


class EyedropperOverlay(QWidget):
    """Transparent full-screen widget that samples the pixel under the cursor."""

    color_picked = Signal(QColor)
    cancelled = Signal()

    # Magnifier sample radius and display size.
    SAMPLE_RADIUS = 32
    PREVIEW_SIZE = 128

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self._screen_shots: list[tuple[QRect, QPixmap]] = []
        self._virtual = QRect()
        self._cursor_pos = QPoint()
        self._active = False

    def begin(self) -> None:
        """Capture every screen and show the overlay across the virtual desktop."""
        if not _has_screen_capture_access():
            _request_screen_capture_access()
            # Re-check after request; if still denied, show a warning.
            if not _has_screen_capture_access():
                QMessageBox.warning(
                    None,
                    "需要屏幕录制权限",
                    "屏幕取色需要屏幕录制权限。\n\n"
                    "请前往 系统设置 > 隐私与安全性 > 屏幕录制，"
                    "允许 FuzzToolBox 访问屏幕。",
                )
                self.cancelled.emit()
                return

        screens = QGuiApplication.screens()
        if not screens:
            self.cancelled.emit()
            return

        self._virtual = QRect()
        for screen in screens:
            self._virtual = self._virtual.united(screen.geometry())

        self._screen_shots = []
        for screen in screens:
            pixmap = screen.grabWindow(0)
            self._screen_shots.append((screen.geometry(), pixmap))

        self._active = True
        self.setGeometry(self._virtual)
        self.showFullScreen()
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
