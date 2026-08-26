"""Small reusable controls used by the screenshot overlay."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRect, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollBar,
    QSlider,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
)

from fuzztoolbox.ui.animations import motion_enabled


class ShadowCheckBox(QAbstractButton):
    """Theme-stable animated checkbox for the capture output shadow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("阴影")
        self.setFixedSize(58, 22)
        self._progress = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._animation.valueChanged.connect(self._set_progress)
        self.toggled.connect(self._animate_toggle)

    def _set_progress(self, value):
        self._progress = float(value)
        self.update()

    def _animate_toggle(self, checked):
        target = 1.0 if checked else 0.0
        if not motion_enabled():
            self._animation.stop()
            self._set_progress(target)
            return
        self._animation.stop()
        self._animation.setStartValue(self._progress)
        self._animation.setEndValue(target)
        self._animation.start()

    @staticmethod
    def _blend(start, end, progress):
        return QColor(
            round(start.red() + (end.red() - start.red()) * progress),
            round(start.green() + (end.green() - start.green()) * progress),
            round(start.blue() + (end.blue() - start.blue()) * progress),
        )

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        indicator = QRectF(1, 3, 16, 16)
        border = QColor("#79bdff") if self.underMouse() else QColor("#6b7d96")
        painter.setPen(QPen(self._blend(border, QColor("#409eff"), self._progress), 1))
        painter.setBrush(
            self._blend(QColor("#172230"), QColor("#409eff"), self._progress)
        )
        painter.drawRoundedRect(indicator, 4, 4)

        check_color = QColor("#ffffff")
        check_color.setAlpha(round(255 * self._progress))
        painter.setPen(QPen(check_color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(5, 11, 8, 14)
        painter.drawLine(8, 14, 14, 7)

        painter.setPen(QColor("#edf2f7" if self.isChecked() else "#c4cedb"))
        painter.drawText(QRectF(23, 0, 35, 22), Qt.AlignLeft | Qt.AlignVCenter, "阴影")


class SelectionOptionsBar(QFrame):
    """Compact selection metadata and output-shape controls."""

    radius_changed = Signal(int)
    shadow_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("screenshotSelectionOptions")
        self.setCursor(Qt.ArrowCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 5)
        layout.setSpacing(9)
        self.resolution_label = QLabel("0 × 0")
        self.resolution_label.setObjectName("screenshotSelectionResolution")
        layout.addWidget(self.resolution_label)
        corner_label = QLabel("圆角")
        corner_label.setObjectName("screenshotSelectionLabel")
        layout.addWidget(corner_label)
        self.radius_slider = SmoothSlider(Qt.Horizontal)
        self.radius_slider.setObjectName("screenshotCornerSlider")
        self.radius_slider.setRange(0, 0)
        self.radius_slider.setFixedWidth(132)
        layout.addWidget(self.radius_slider)
        self.radius_value = QLabel("0")
        self.radius_value.setObjectName("screenshotSelectionValue")
        self.radius_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.radius_value.setFixedWidth(34)
        layout.addWidget(self.radius_value)
        self.shadow_checkbox = ShadowCheckBox()
        self.shadow_checkbox.setObjectName("screenshotShadowCheckbox")
        self.shadow_checkbox.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.shadow_checkbox)
        self.radius_slider.valueChanged.connect(self._radius_value_changed)
        self.shadow_checkbox.toggled.connect(self.shadow_toggled)
        self.setFixedHeight(34)
        self.setFixedWidth(self.sizeHint().width())

    def set_selection(self, resolution, radius, shadow_enabled):
        self.resolution_label.setText(
            f"{resolution.width()} × {resolution.height()}"
        )
        self.radius_slider.setRange(0, 100)
        self.radius_slider.setValue(min(max(0, radius), 100))
        self.shadow_checkbox.setChecked(shadow_enabled)

    def _radius_value_changed(self, value):
        self.radius_value.setText(str(value))
        self.radius_changed.emit(value)


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
