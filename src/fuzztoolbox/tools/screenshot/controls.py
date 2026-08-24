"""Small reusable controls used by the screenshot overlay."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QPushButton,
    QScrollBar,
    QSlider,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
)


class ColorSwatchButton(QPushButton):
    """Small painted swatch that avoids runtime stylesheet generation."""

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setCheckable(True)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(
            QPen(
                QColor("#ffffff") if self.isChecked() else QColor("#667085"),
                3 if self.isChecked() else 1,
            )
        )
        painter.setBrush(self.color)
        painter.drawEllipse(self.rect().adjusted(3, 3, -3, -3))


class ColorValueButton(QPushButton):
    """Toolbar button with an independently colored HEX value."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.display_color = QColor("#ff4d4f")
        self.setAccessibleName("颜色")

    def set_display_color(self, color):
        self.display_color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        painter = QStylePainter(self)
        painter.drawControl(QStyle.CE_PushButton, option)

        label = "颜色 "
        value = self.display_color.name().upper()
        metrics = painter.fontMetrics()
        total_width = metrics.horizontalAdvance(label + value)
        x = (self.width() - total_width) // 2
        baseline = (self.height() + metrics.ascent() - metrics.descent()) // 2
        painter.setPen(QColor("#edf2f7"))
        painter.drawText(x, baseline, label)
        x += metrics.horizontalAdvance(label)
        painter.setPen(self.display_color)
        painter.drawText(x, baseline, value)


class SmoothSlider(QSlider):
    """Slider whose handle follows the pointer instead of page-stepping."""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._set_from_position(event.position().x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._set_from_position(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _set_from_position(self, position):
        span = max(1.0, self.width() - 14.0)
        ratio = min(1.0, max(0.0, (position - 7.0) / span))
        self.setValue(round(self.minimum() + ratio * (self.maximum() - self.minimum())))


class ScreenshotScrollBar(QScrollBar):
    """Theme-painted scrollbar that bypasses the macOS native focus frame."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_MacShowFocusRect, False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#172230"))
        track = self.rect().adjusted(2, 2, -2, -2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#172230"))
        painter.drawRoundedRect(track, 4, 4)
        handle = self._handle_rect(track)
        painter.setBrush(QColor("#6b7d96" if self.underMouse() else "#526176"))
        painter.drawRoundedRect(handle, 4, 4)

    def _handle_rect(self, track):
        extent = track.height() if self.orientation() == Qt.Vertical else track.width()
        total = max(1, self.maximum() - self.minimum() + self.pageStep())
        handle_extent = min(extent, max(28, round(extent * self.pageStep() / total)))
        travel = max(0, extent - handle_extent)
        value_range = max(1, self.maximum() - self.minimum())
        offset = round(travel * (self.value() - self.minimum()) / value_range)
        if self.orientation() == Qt.Vertical:
            return QRect(track.left(), track.top() + offset, track.width(), handle_extent)
        return QRect(track.left() + offset, track.top(), handle_extent, track.height())

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)
