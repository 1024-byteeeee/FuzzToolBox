"""Full-desktop screenshot selection and annotation overlay."""

from __future__ import annotations

import math
import platform
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QRect,
    QRectF,
    QSize,
    QStandardPaths,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFontMetrics,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygon,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QColorDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollBar,
    QSlider,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QWidget,
)

from fuzztoolbox.tools.color_picker.eyedropper import _grab_screen, _raise_window_level
from fuzztoolbox.ui.style_loader import apply_style

from .window_detection import enumerate_window_rects


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
        painter.setPen(QPen(QColor("#ffffff") if self.isChecked() else QColor("#667085"),
                            3 if self.isChecked() else 1))
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


class ScreenshotOverlay(QWidget):
    completed = Signal()
    cancelled = Signal()
    _screens_ready = Signal(list)

    TOOLS = (("矩形", "rect"), ("椭圆", "ellipse"), ("箭头", "arrow"),
             ("画笔", "pen"), ("文字", "text"), ("马赛克", "mosaic"))
    COLORS = (QColor("#ff4d4f"), QColor("#409eff"), QColor("#19be6b"),
              QColor("#ffd43b"), QColor("#ffffff"), QColor("#202124"))
    TOOLBAR_HEIGHT = 50

    def __init__(self, parent=None, *, include_app_window=False):
        super().__init__(parent)
        self._include_app_window = include_app_window
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        apply_style(self, "tools.screenshot.overlay:workspace")
        self._shots = []
        self._virtual = QRect()
        self._desktop = QPixmap()
        self._dpr = 1.0
        self.selection = QRect()
        self._drag_start = QPoint()
        self._drag_mode = ""
        self._handle = ""
        self._selection_start = QRect()
        self._annotations = []
        self._current = None
        self._tool = ""
        self._color_index = 0
        self._color = QColor(self.COLORS[self._color_index])
        self._width = 4
        self._font_size = 20
        self._font_family = self.font().family()
        self._cursor_pos = QPoint()
        self._text_editor = None
        self._active_annotation = None
        self._editing_text_index = -1
        self._moving_text = None
        self._moving_text_start = QPoint()
        self._color_dialog = None
        self._save_dialog = None
        self._closing = False
        self._input_lock_installed = False
        self._window_candidates = []
        self._screen_candidates = []
        self._hovered_window = QRect()
        self._pending_window = QRect()
        self._screens_ready.connect(self._show_overlay)
        self._build_toolbar()
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._escape_shortcut.setContext(Qt.ApplicationShortcut)
        self._escape_shortcut.activated.connect(self._cancel)

    def _build_toolbar(self):
        self.toolbar = QFrame(self)
        self.toolbar.setObjectName("screenshotToolbar")
        layout = QHBoxLayout(self.toolbar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignVCenter)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(False)
        self._tool_buttons = {}
        for label, tool in self.TOOLS:
            button = QPushButton(label)
            button.setObjectName("screenshotToolButton")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, value=tool: self._select_tool(value, checked)
            )
            self.tool_group.addButton(button)
            self._tool_buttons[tool] = button
            layout.addWidget(button)
        self.color_button = ColorValueButton()
        self.color_button.setObjectName("screenshotColorButton")
        self.color_button.setFixedWidth(108)
        self.color_button.clicked.connect(self._toggle_color_palette)
        layout.addWidget(self.color_button)
        self.width_button = QPushButton("粗细 4")
        self.width_button.clicked.connect(self._toggle_width_panel)
        layout.addWidget(self.width_button)
        self.font_size_button = QPushButton("字号 20")
        self.font_size_button.clicked.connect(self._toggle_font_size_panel)
        layout.addWidget(self.font_size_button)
        self.font_button = QPushButton()
        self.font_button.setFixedWidth(138)
        self.font_button.clicked.connect(self._toggle_font_panel)
        layout.addWidget(self.font_button)
        undo = QPushButton("撤销")
        undo.clicked.connect(self._undo)
        layout.addWidget(undo)
        save = QPushButton("保存")
        save.clicked.connect(self._save)
        layout.addWidget(save)
        finish = QPushButton("完成")
        finish.setObjectName("screenshotFinishButton")
        finish.clicked.connect(self._copy_and_finish)
        layout.addWidget(finish)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self._cancel)
        layout.addWidget(cancel)
        for button in self.toolbar.findChildren(
            QPushButton, options=Qt.FindDirectChildrenOnly
        ):
            button.setFixedHeight(38)
            button.ensurePolished()
        self.toolbar.ensurePolished()
        self.toolbar.resize(self.toolbar.sizeHint().width(), self.TOOLBAR_HEIGHT)
        self._center_toolbar_buttons()
        self.toolbar.hide()
        self._build_color_palette()
        self._build_width_panel()
        self._build_font_size_panel()
        self._build_font_panel()
        self._refresh_font_button()
        self._refresh_color_button()

    def _build_color_palette(self):
        self.color_palette = QFrame(self)
        self.color_palette.setObjectName("screenshotPopup")
        layout = QGridLayout(self.color_palette)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setHorizontalSpacing(7)
        layout.setVerticalSpacing(10)
        self._swatches = []
        palette = (
            "#ff4d4f", "#ff8a00", "#ffd43b", "#19be6b",
            "#00b8d9", "#409eff", "#7c4dff", "#d946ef",
            "#ffffff", "#aeb6c2", "#202124", "#000000",
        )
        for index, value in enumerate(palette):
            swatch = ColorSwatchButton(value, self.color_palette)
            swatch.clicked.connect(
                lambda checked=False, color=value: self._choose_color(QColor(color))
            )
            layout.addWidget(swatch, index // 6, index % 6)
            self._swatches.append(swatch)
        custom = QPushButton("自定义颜色")
        self.custom_color_button = custom
        custom.setObjectName("screenshotPopupButton")
        custom.setFixedHeight(32)
        custom.clicked.connect(self._choose_custom_color)
        layout.addWidget(custom, 2, 0, 1, 6)
        layout.setRowMinimumHeight(0, 28)
        layout.setRowMinimumHeight(1, 28)
        layout.setRowMinimumHeight(2, 32)
        self.color_palette.adjustSize()
        self.color_palette.setFixedSize(self.color_palette.sizeHint())
        self.color_palette.hide()

    def _build_width_panel(self):
        self.width_panel = QFrame(self)
        self.width_panel.setObjectName("screenshotPopup")
        layout = QHBoxLayout(self.width_panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        label = QLabel("粗细")
        layout.addWidget(label)
        self.width_slider = SmoothSlider(Qt.Horizontal)
        self.width_slider.setRange(10, 400)
        self.width_slider.setValue(round(self._width * 10))
        self.width_slider.setMinimumWidth(150)
        layout.addWidget(self.width_slider)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1, 40)
        self.width_spin.setDecimals(1)
        self.width_spin.setSingleStep(0.1)
        self.width_spin.setValue(self._width)
        self.width_spin.setSuffix(" px")
        self.width_spin.setFixedWidth(90)
        layout.addWidget(self.width_spin)
        self.width_slider.valueChanged.connect(
            lambda value: self.width_spin.setValue(value / 10)
        )
        self.width_spin.valueChanged.connect(
            lambda value: self.width_slider.setValue(round(value * 10))
        )
        self.width_spin.valueChanged.connect(self._set_width)
        self.width_panel.adjustSize()
        self.width_panel.hide()

    def _build_font_size_panel(self):
        self.font_size_panel = QFrame(self)
        self.font_size_panel.setObjectName("screenshotPopup")
        layout = QHBoxLayout(self.font_size_panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        label = QLabel("字号")
        layout.addWidget(label)
        self.font_size_slider = SmoothSlider(Qt.Horizontal)
        self.font_size_slider.setRange(100, 1000)
        self.font_size_slider.setValue(round(self._font_size * 10))
        self.font_size_slider.setMinimumWidth(150)
        layout.addWidget(self.font_size_slider)
        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(10, 100)
        self.font_size_spin.setDecimals(1)
        self.font_size_spin.setSingleStep(0.5)
        self.font_size_spin.setValue(self._font_size)
        self.font_size_spin.setSuffix(" px")
        self.font_size_spin.setFixedWidth(104)
        layout.addWidget(self.font_size_spin)
        self.font_size_slider.valueChanged.connect(
            lambda value: self.font_size_spin.setValue(value / 10)
        )
        self.font_size_spin.valueChanged.connect(
            lambda value: self.font_size_slider.setValue(round(value * 10))
        )
        self.font_size_spin.valueChanged.connect(self._set_font_size)
        self.font_size_panel.adjustSize()
        self.font_size_panel.hide()

    def _build_font_panel(self):
        self.font_panel = QFrame(self)
        self.font_panel.setObjectName("screenshotPopup")
        layout = QHBoxLayout(self.font_panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(QLabel("字体"))
        self.font_combo = QFontComboBox()
        self.font_combo.setObjectName("screenshotFontCombo")
        font_view = self.font_combo.view()
        font_view.setObjectName("screenshotFontList")
        font_view.setFrameShape(QFrame.NoFrame)
        font_view.setAttribute(Qt.WA_MacShowFocusRect, False)
        font_scrollbar = ScreenshotScrollBar(Qt.Vertical, font_view)
        font_view.setVerticalScrollBar(font_scrollbar)
        font_scrollbar.setObjectName("screenshotFontScrollBar")
        font_scrollbar.setFocusPolicy(Qt.NoFocus)
        font_scrollbar.setAttribute(Qt.WA_MacShowFocusRect, False)
        apply_style(font_view, "tools.screenshot.overlay.font_list")
        apply_style(font_scrollbar, "tools.screenshot.overlay.font_scrollbar")
        self.font_combo.setMinimumWidth(240)
        self.font_combo.setCurrentFont(self.font())
        self.font_combo.currentFontChanged.connect(
            lambda font: self._set_font_family(font.family())
        )
        layout.addWidget(self.font_combo)
        self.font_panel.adjustSize()
        self.font_panel.hide()

    def begin(self):
        screens = QGuiApplication.screens()
        if not screens:
            self.cancelled.emit()
            return
        self._virtual = QRect()
        for screen in screens:
            self._virtual = self._virtual.united(screen.geometry())
        if platform.system() != "Darwin":
            self._show_overlay([(screen.geometry(), _grab_screen(screen)) for screen in screens])
            return

        def capture():
            try:
                self._screens_ready.emit(
                    [(screen.geometry(), _grab_screen(screen)) for screen in screens]
                )
            except Exception:  # noqa: BLE001 - capture failures must restore the app
                self.cancelled.emit()

        threading.Thread(target=capture, daemon=True).start()

    def _show_overlay(self, shots):
        self._closing = False
        self._install_input_lock()
        self._shots = shots
        self._dpr = max((pixmap.devicePixelRatio() for _, pixmap in shots), default=1.0)
        size = self._virtual.size()
        self._desktop = QPixmap(round(size.width() * self._dpr), round(size.height() * self._dpr))
        self._desktop.setDevicePixelRatio(self._dpr)
        self._desktop.fill(Qt.black)
        painter = QPainter(self._desktop)
        for geometry, pixmap in shots:
            target = QRect(geometry.topLeft() - self._virtual.topLeft(), geometry.size())
            painter.drawPixmap(QRectF(target), pixmap, QRectF(pixmap.rect()))
        painter.end()
        native_candidates = []
        for window_rect in enumerate_window_rects(
            include_current_process=self._include_app_window
        ):
            local_rect = window_rect.translated(-self._virtual.topLeft()).intersected(
                QRect(QPoint(), self._virtual.size())
            )
            if local_rect.width() >= 12 and local_rect.height() >= 12:
                native_candidates.append(local_rect)
        self._screen_candidates = []
        dock_fallbacks = []
        for screen in QGuiApplication.screens():
            geometry = screen.geometry().translated(-self._virtual.topLeft())
            self._screen_candidates.append(geometry)
            if platform.system() == "Darwin":
                available = screen.availableGeometry().translated(
                    -self._virtual.topLeft()
                )
                dock_fallbacks.extend(self._macos_dock_regions(geometry, available))
        self._window_candidates = self._unique_regions(
            dock_fallbacks + native_candidates
        )
        self._lock_overlay_geometry(self._virtual)
        self._cursor_pos = self.mapFromGlobal(QGuiApplication.primaryScreen().geometry().center())
        self.show()
        _raise_window_level(self)
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _lock_overlay_geometry(self, geometry):
        """Make the frozen desktop overlay impossible to resize natively."""
        self.setFixedSize(geometry.size())
        self.move(geometry.topLeft())

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.drawPixmap(QRectF(self.rect()), self._desktop, QRectF(self._desktop.rect()))
        painter.fillRect(self.rect(), QColor(0, 0, 0, 112))
        if self.selection.isValid() and self.selection.width() > 1:
            painter.drawPixmap(QRectF(self.selection), self._desktop, QRectF(
                self.selection.x() * self._dpr,
                self.selection.y() * self._dpr,
                self.selection.width() * self._dpr,
                self.selection.height() * self._dpr,
            ))
            painter.save()
            painter.setClipRect(self.selection)
            for annotation in self._annotations:
                self._paint_annotation(painter, annotation)
            if self._current:
                self._paint_annotation(painter, self._current)
            painter.restore()
            painter.setPen(QPen(QColor("#55b6ff"), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.selection)
            self._paint_handles(painter)
            self._paint_size_badge(painter)
        else:
            if self._hovered_window.isValid():
                painter.drawPixmap(
                    QRectF(self._hovered_window),
                    self._desktop,
                    QRectF(
                        self._hovered_window.x() * self._dpr,
                        self._hovered_window.y() * self._dpr,
                        self._hovered_window.width() * self._dpr,
                        self._hovered_window.height() * self._dpr,
                    ),
                )
                painter.setPen(QPen(QColor("#55b6ff"), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(self._hovered_window.adjusted(1, 1, -1, -1))
            self._paint_magnifier(painter)

    def _paint_annotation(self, painter, annotation):
        kind = annotation["kind"]
        color = annotation["color"]
        width = annotation["width"]
        painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        if kind == "rect":
            painter.drawRect(QRect(annotation["start"], annotation["end"]).normalized())
        elif kind == "ellipse":
            painter.drawEllipse(QRect(annotation["start"], annotation["end"]).normalized())
        elif kind == "pen":
            path = QPainterPath(annotation["points"][0])
            for point in annotation["points"][1:]:
                path.lineTo(point)
            painter.drawPath(path)
        elif kind == "arrow":
            self._paint_arrow(painter, annotation["start"], annotation["end"], color, width)
        elif kind == "text":
            font = painter.font()
            font.setFamily(annotation.get("font_family", self.font().family()))
            font.setPixelSize(round(annotation["font_size"]))
            font.setBold(True)
            painter.setFont(font)
            text_rect = QRect(
                annotation["start"], annotation.get("size", QRect(0, 0, 260, 44).size())
            )
            painter.drawText(
                text_rect, Qt.AlignLeft | Qt.AlignVCenter, annotation["text"]
            )
        elif kind == "mosaic":
            self._paint_mosaic_stroke(painter, annotation)

    def _paint_arrow(self, painter, start, end, color, width):
        painter.drawLine(start, end)
        angle = math.atan2(start.y() - end.y(), start.x() - end.x())
        length = max(12, width * 4)
        points = [end]
        for delta in (-0.55, 0.55):
            points.append(QPoint(
                round(end.x() + math.cos(angle + delta) * length),
                round(end.y() + math.sin(angle + delta) * length),
            ))
        painter.setBrush(color)
        painter.drawPolygon(QPolygon(points))

    def _paint_mosaic_rect(self, painter, rect):
        rect = rect.intersected(self.selection)
        if rect.isEmpty():
            return
        source = self._desktop.copy(QRect(
            round(rect.x() * self._dpr), round(rect.y() * self._dpr),
            round(rect.width() * self._dpr), round(rect.height() * self._dpr),
        ))
        tiny = source.scaled(max(1, rect.width() // 12), max(1, rect.height() // 12),
                             Qt.IgnoreAspectRatio, Qt.FastTransformation)
        pixelated = tiny.scaled(rect.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
        painter.drawPixmap(rect, pixelated)

    def _paint_mosaic_stroke(self, painter, annotation):
        diameter = max(8, round(annotation["width"] * 3))
        radius = diameter // 2
        for point in annotation["points"]:
            rect = QRect(point.x() - radius, point.y() - radius, diameter, diameter)
            painter.save()
            clip = QPainterPath()
            clip.addEllipse(QRectF(rect))
            painter.setClipPath(clip, Qt.IntersectClip)
            self._paint_mosaic_rect(painter, rect)
            painter.restore()

    def _paint_handles(self, painter):
        painter.setPen(QPen(Qt.white, 1))
        painter.setBrush(QColor("#55b6ff"))
        for point in self._handle_points().values():
            painter.drawRect(QRect(point.x() - 4, point.y() - 4, 8, 8))

    def _paint_size_badge(self, painter):
        resolution = self._selection_pixel_size()
        text = f"{resolution.width()} × {resolution.height()}"
        badge_width = max(112, painter.fontMetrics().horizontalAdvance(text) + 20)
        badge = QRect(
            self.selection.left(),
            max(4, self.selection.top() - 28),
            badge_width,
            23,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(20, 26, 34, 220))
        painter.drawRoundedRect(badge, 5, 5)
        painter.setPen(Qt.white)
        painter.drawText(badge, Qt.AlignCenter, text)

    def _paint_magnifier(self, painter):
        pos = self._cursor_pos
        sample = QRect(max(0, pos.x() - 7), max(0, pos.y() - 7), 15, 15)
        image = self._desktop.copy(QRect(
            round(sample.x() * self._dpr), round(sample.y() * self._dpr),
            round(sample.width() * self._dpr), round(sample.height() * self._dpr),
        ))
        target = self._magnifier_rect(pos)
        painter.drawPixmap(
            target,
            image.scaled(target.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation),
        )
        color = self._color_at(pos)
        center = target.center()
        painter.setPen(QPen(Qt.white, 1))
        painter.drawLine(target.left(), center.y(), target.right(), center.y())
        painter.drawLine(center.x(), target.top(), center.x(), target.bottom())
        painter.setPen(QPen(QColor("#111827"), 1))
        painter.drawRect(QRect(center.x() - 5, center.y() - 5, 10, 10))
        footer = QRect(target.x(), target.bottom() - 27, target.width(), 28)
        painter.fillRect(footer, color)
        brightness = color.red() * 299 + color.green() * 587 + color.blue() * 114
        painter.setPen(Qt.black if brightness > 150000 else Qt.white)
        painter.drawText(footer, Qt.AlignCenter, color.name().upper())
        painter.setPen(QPen(QColor("#55b6ff"), 2))
        painter.drawRect(target.adjusted(0, 0, -1, -1))

    def _magnifier_rect(self, pos):
        target = QRect(pos.x() + 20, pos.y() + 20, 144, 144)
        if target.right() > self.width():
            target.moveLeft(pos.x() - 164)
        if target.bottom() > self.height():
            target.moveTop(pos.y() - 164)
        return target

    def _color_at(self, point):
        image = self._desktop.toImage()
        x = min(image.width() - 1, max(0, round(point.x() * self._dpr)))
        y = min(image.height() - 1, max(0, round(point.y() * self._dpr)))
        return image.pixelColor(x, y)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        point = event.position().toPoint()
        self._hide_popups()
        self._drag_start = point
        if not self.selection.isValid():
            window_rect = self._window_at(point)
            if window_rect.isValid():
                self._drag_mode = "window_pending"
                self._pending_window = QRect(window_rect)
            else:
                self._drag_mode = "select"
                self.selection = QRect(point, point)
            return
        handle = self._hit_handle(point)
        if handle:
            self._drag_mode = "resize"
            self._handle = handle
            self._selection_start = QRect(self.selection)
            return
        annotation = self._annotation_at(point)
        if annotation is not None:
            self._select_annotation(annotation)
            if annotation["kind"] == "text":
                self._drag_mode = "move_text"
                self._moving_text = annotation
                self._moving_text_start = QPoint(annotation["start"])
            else:
                self._drag_mode = "element_selected"
            return
        self._active_annotation = None
        if self._tool and self.selection.contains(point):
            if self._tool == "text":
                self._begin_text_edit(point)
                return
            self._drag_mode = "annotate"
            self._current = self._new_annotation(self._tool, point, point)
            return
        if self.selection.contains(point):
            self._drag_mode = "move"
            self._selection_start = QRect(self.selection)
        else:
            self._annotations.clear()
            self.selection = QRect(point, point)
            self._drag_mode = "select"
            self.toolbar.hide()

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        self._cursor_pos = point
        if not self.selection.isValid() and not self._drag_mode:
            self._hovered_window = self._window_at(point)
        if self._drag_mode == "window_pending":
            if (point - self._drag_start).manhattanLength() > 4:
                self._drag_mode = "select"
                self._pending_window = QRect()
                self.selection = QRect(self._drag_start, point).normalized().intersected(
                    self.rect()
                )
        elif self._drag_mode == "select":
            self.selection = QRect(self._drag_start, point).normalized().intersected(self.rect())
        elif self._drag_mode == "move":
            moved = self._selection_start.translated(point - self._drag_start)
            if self.rect().contains(moved):
                delta = moved.topLeft() - self.selection.topLeft()
                self.selection = moved
                self._translate_annotations(delta)
        elif self._drag_mode == "resize":
            self._resize_selection(point)
        elif self._drag_mode == "move_text" and self._moving_text is not None:
            self._move_text_annotation(point)
        elif self._drag_mode == "annotate" and self._current:
            self._current["end"] = point
            if self._current["kind"] in ("pen", "mosaic"):
                self._append_brush_points(self._current, point)
        elif not self._drag_mode:
            self._refresh_hover_cursor(point)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._drag_mode == "window_pending":
            self.selection = QRect(self._pending_window)
            self._pending_window = QRect()
            self._hovered_window = QRect()
        if self._drag_mode == "annotate" and self._current:
            self._annotations.append(self._current)
            self._current = None
        if self.selection.width() >= 8 and self.selection.height() >= 8:
            self._position_toolbar()
            self.toolbar.show()
            self._center_toolbar_buttons()
        else:
            self.selection = QRect()
            self.toolbar.hide()
        self._drag_mode = ""
        self._moving_text = None
        self._refresh_hover_cursor(event.position().toPoint())
        self.update()

    def mouseDoubleClickEvent(self, event):
        point = event.position().toPoint()
        annotation = self._text_at(point)
        if annotation is not None:
            self._begin_text_edit(annotation["start"], annotation=annotation)
            event.accept()
            return
        if self.selection.contains(point):
            self._copy_and_finish()

    def keyPressEvent(self, event):
        if self._is_zoom_shortcut(event):
            event.accept()
        elif event.key() == Qt.Key_Escape:
            self._cancel()
        elif event.key() == Qt.Key_Space:
            screen = self._screen_at(self._cursor_pos)
            if screen.isValid():
                self.selection = screen
                self._hovered_window = QRect()
                self._position_toolbar()
                self.toolbar.show()
                self._center_toolbar_buttons()
                self.update()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.selection.isValid():
            self._copy_and_finish()
        elif event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier) and event.key() == Qt.Key_Z:
            self._undo()
        else:
            super().keyPressEvent(event)

    @staticmethod
    def _is_zoom_shortcut(event):
        modifiers = event.modifiers()
        if not modifiers & (Qt.ControlModifier | Qt.MetaModifier):
            return False
        return event.key() in (
            Qt.Key_Plus,
            Qt.Key_Minus,
            Qt.Key_Equal,
            Qt.Key_Underscore,
            Qt.Key_0,
        )

    def wheelEvent(self, event):
        # A screenshot is a frozen desktop snapshot. Consuming wheel events
        # prevents Ctrl/Command-wheel and touchpad scroll gestures from being
        # forwarded to a zoomable window underneath the transparent overlay.
        event.accept()

    def event(self, event):
        if event.type() in (QEvent.NativeGesture, QEvent.Gesture):
            event.accept()
            return True
        return super().event(event)

    def hideEvent(self, event):
        self._remove_input_lock()
        super().hideEvent(event)

    def _new_annotation(self, kind, start, end, **extra):
        annotation = {"kind": kind, "start": QPoint(start), "end": QPoint(end),
                      "color": QColor(self._color), "width": self._width}
        if kind in ("pen", "mosaic"):
            annotation["points"] = [QPoint(start)]
        annotation.update(extra)
        return annotation

    @staticmethod
    def _append_brush_points(annotation, point):
        previous = annotation["points"][-1]
        distance = math.hypot(point.x() - previous.x(), point.y() - previous.y())
        spacing = max(1.0, annotation["width"] * 0.7)
        steps = max(1, math.ceil(distance / spacing))
        for index in range(1, steps + 1):
            ratio = index / steps
            annotation["points"].append(QPoint(
                round(previous.x() + (point.x() - previous.x()) * ratio),
                round(previous.y() + (point.y() - previous.y()) * ratio),
            ))

    def _select_tool(self, tool, checked=True):
        self._commit_text()
        if checked:
            for other_tool, button in self._tool_buttons.items():
                if other_tool != tool:
                    button.setChecked(False)
            self._tool = tool
        else:
            self._tool = ""
        self._refresh_cursor()

    def _toggle_color_palette(self):
        self.width_panel.hide()
        self.font_size_panel.hide()
        self.font_panel.hide()
        if self.color_palette.isVisible():
            self.color_palette.hide()
            return
        self._position_popup(self.color_palette, self.color_button)
        self.color_palette.show()
        self.color_palette.layout().activate()
        self.color_palette.raise_()

    def _choose_color(self, color):
        self._color = QColor(color)
        if self._active_annotation is not None:
            self._active_annotation["color"] = QColor(self._color)
            if self._text_editor is not None:
                self._text_editor.setProperty("annotationColor", self._color)
            self.update()
        self.color_palette.hide()
        self._refresh_color_button()

    def _choose_custom_color(self):
        self.color_palette.hide()
        if self._color_dialog is not None:
            self._color_dialog.raise_()
            self._color_dialog.activateWindow()
            return
        dialog = QColorDialog(self._color, self)
        dialog.setWindowTitle("选择标注颜色")
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self._translate_color_dialog(dialog)
        dialog.accepted.connect(lambda: self._choose_color(dialog.selectedColor()))
        dialog.finished.connect(self._color_dialog_closed)
        self._color_dialog = dialog
        dialog.open()
        _raise_window_level(dialog)
        dialog.raise_()
        dialog.activateWindow()

    @staticmethod
    def _translate_color_dialog(dialog):
        button_texts = {
            "&Pick Screen Color": "屏幕取色",
            "&Add to Custom Colors": "添加到自定义颜色",
            "OK": "确定",
            "Cancel": "取消",
        }
        label_texts = {
            "&Basic colors": "基本颜色",
            "&Custom colors": "自定义颜色",
            "Hu&e:": "色相：",
            "&Sat:": "饱和度：",
            "&Val:": "明度：",
            "&Red:": "红：",
            "&Green:": "绿：",
            "Bl&ue:": "蓝：",
            "A&lpha channel:": "透明度：",
            "&HTML:": "HEX：",
        }
        for button in dialog.findChildren(QAbstractButton):
            if button.text() in button_texts:
                button.setText(button_texts[button.text()])
        for label in dialog.findChildren(QLabel):
            if label.text() in label_texts:
                label.setText(label_texts[label.text()])

    def _color_dialog_closed(self):
        dialog = self._color_dialog
        self._color_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    def _refresh_color_button(self):
        self.color_button.setProperty("colorValue", self._color.name())
        self.color_button.set_display_color(self._color)
        for swatch in self._swatches:
            swatch.setChecked(swatch.color == self._color)
        self.color_button.style().unpolish(self.color_button)
        self.color_button.style().polish(self.color_button)

    def _toggle_width_panel(self):
        self.color_palette.hide()
        self.font_size_panel.hide()
        self.font_panel.hide()
        if self.width_panel.isVisible():
            self.width_panel.hide()
            return
        self._position_popup(self.width_panel, self.width_button)
        self.width_panel.show()
        self.width_panel.raise_()

    def _toggle_font_size_panel(self):
        self.color_palette.hide()
        self.width_panel.hide()
        self.font_panel.hide()
        if self.font_size_panel.isVisible():
            self.font_size_panel.hide()
            return
        self._position_popup(self.font_size_panel, self.font_size_button)
        self.font_size_panel.show()
        self.font_size_panel.raise_()

    def _toggle_font_panel(self):
        self.color_palette.hide()
        self.width_panel.hide()
        self.font_size_panel.hide()
        if self.font_panel.isVisible():
            self.font_panel.hide()
            return
        self._position_popup(self.font_panel, self.font_button)
        self.font_panel.show()
        self.font_panel.raise_()

    def _set_width(self, value):
        self._width = float(value)
        self.width_button.setText(f"粗细 {value:g}")
        if self._active_annotation is not None:
            self._active_annotation["width"] = self._width
            if self._text_editor is not None:
                self._text_editor.setProperty("annotationWidth", self._width)
            self.update()
        self._refresh_cursor()

    def _set_font_size(self, value):
        self._font_size = float(value)
        self.font_size_button.setText(f"字号 {value:g}")
        if self._text_editor is not None:
            self._text_editor.setProperty("annotationFontSize", self._font_size)
            self._apply_editor_font(self._text_editor)
        if (
            self._active_annotation is not None
            and self._active_annotation["kind"] == "text"
        ):
            self._active_annotation["font_size"] = self._font_size
            self._refresh_text_metrics(self._active_annotation)
            self.update()

    def _set_font_family(self, family):
        self._font_family = family or self.font().family()
        self._refresh_font_button()
        if self._text_editor is not None:
            self._text_editor.setProperty("annotationFontFamily", self._font_family)
            self._apply_editor_font(self._text_editor)
        if (
            self._active_annotation is not None
            and self._active_annotation["kind"] == "text"
        ):
            self._active_annotation["font_family"] = self._font_family
            self._refresh_text_metrics(self._active_annotation)
            self.update()

    def _refresh_font_button(self):
        metrics = QFontMetrics(self.font_button.font())
        family = metrics.elidedText(self._font_family, Qt.ElideRight, 88)
        self.font_button.setText(f"字体 {family}")
        self.font_button.setToolTip(self._font_family)

    def _refresh_cursor(self):
        if self._tool != "mosaic":
            self.setCursor(Qt.CrossCursor)
            return
        diameter = min(96, max(8, round(self._width * 3)))
        size = diameter + 6
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 190), 3))
        painter.drawEllipse(QRectF(3, 3, diameter, diameter))
        painter.setPen(QPen(Qt.white, 1))
        painter.drawEllipse(QRectF(3, 3, diameter, diameter))
        painter.end()
        self.setCursor(QCursor(pixmap, size // 2, size // 2))

    def _position_popup(self, popup, anchor):
        popup.adjustSize()
        anchor_pos = anchor.mapTo(self, QPoint())
        x = min(max(8, anchor_pos.x()), self.width() - popup.width() - 8)
        y = anchor_pos.y() - popup.height() - 8
        if y < 8:
            y = anchor_pos.y() + anchor.height() + 8
        popup.move(x, y)

    def _hide_popups(self):
        self.color_palette.hide()
        self.width_panel.hide()
        self.font_size_panel.hide()
        self.font_panel.hide()

    def _begin_text_edit(self, point, *, annotation=None):
        self._commit_text()
        text = ""
        if annotation is not None:
            self._editing_text_index = self._annotations.index(annotation)
            self._annotations.pop(self._editing_text_index)
            self._active_annotation = annotation
            point = QPoint(annotation["start"])
            text = annotation["text"]
            self._color = QColor(annotation["color"])
            self._width = float(annotation["width"])
            self.width_spin.setValue(self._width)
            self.font_size_spin.setValue(float(annotation["font_size"]))
            family = annotation.get("font_family", self.font().family())
            self.font_combo.setCurrentFont(self._font_with_family(family))
            self._set_font_family(family)
            self._refresh_color_button()
        else:
            self._editing_text_index = -1
            self._active_annotation = None
        editor = QLineEdit(self)
        editor.setObjectName("screenshotTextEditor")
        editor.setPlaceholderText("输入文字，按回车确认")
        editor.setProperty("annotationPoint", point)
        editor.setProperty("annotationColor", self._color)
        editor.setProperty("annotationWidth", self._width)
        editor.setProperty("annotationFontSize", self._font_size)
        editor.setProperty("annotationFontFamily", self._font_family)
        editor.setText(text)
        self._apply_editor_font(editor)
        width = min(280, max(120, self.selection.right() - point.x()))
        editor.setGeometry(
            point.x(), point.y(), width,
            min(38, self.selection.bottom() - point.y() + 1),
        )
        editor.installEventFilter(self)
        editor.show()
        editor.raise_()
        editor.setFocus(Qt.MouseFocusReason)
        if text:
            editor.selectAll()
        self._text_editor = editor

    @staticmethod
    def _text_rect(annotation):
        return QRect(annotation["start"], annotation["size"])

    def _text_at(self, point):
        for annotation in reversed(self._annotations):
            if annotation["kind"] == "text" and self._text_rect(annotation).contains(
                point
            ):
                return annotation
        return None

    def _annotation_at(self, point):
        for annotation in reversed(self._annotations):
            if self._annotation_contains(annotation, point):
                return annotation
        return None

    def _annotation_contains(self, annotation, point):
        kind = annotation["kind"]
        tolerance = max(6.0, float(annotation.get("width", 1)) + 3.0)
        if kind == "text":
            return self._text_rect(annotation).contains(point)
        if kind in ("arrow",):
            return self._distance_to_segment(
                point, annotation["start"], annotation["end"]
            ) <= tolerance
        if kind == "rect":
            rect = QRect(annotation["start"], annotation["end"]).normalized()
            outer = rect.adjusted(-round(tolerance), -round(tolerance),
                                  round(tolerance), round(tolerance))
            inner = rect.adjusted(round(tolerance), round(tolerance),
                                  -round(tolerance), -round(tolerance))
            return outer.contains(point) and (not inner.isValid() or not inner.contains(point))
        if kind == "ellipse":
            rect = QRect(annotation["start"], annotation["end"]).normalized()
            if not rect.adjusted(-round(tolerance), -round(tolerance),
                                 round(tolerance), round(tolerance)).contains(point):
                return False
            rx = max(1.0, rect.width() / 2.0)
            ry = max(1.0, rect.height() / 2.0)
            dx = (point.x() - rect.center().x()) / rx
            dy = (point.y() - rect.center().y()) / ry
            normalized = math.hypot(dx, dy)
            return abs(normalized - 1.0) <= tolerance / min(rx, ry)
        if kind in ("pen", "mosaic"):
            points = annotation.get("points", [])
            if len(points) == 1:
                return math.hypot(
                    point.x() - points[0].x(), point.y() - points[0].y()
                ) <= tolerance
            return any(
                self._distance_to_segment(point, start, end) <= tolerance
                for start, end in zip(points, points[1:])
            )
        return False

    @staticmethod
    def _distance_to_segment(point, start, end):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        if dx == 0 and dy == 0:
            return math.hypot(point.x() - start.x(), point.y() - start.y())
        ratio = ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / (
            dx * dx + dy * dy
        )
        ratio = min(1.0, max(0.0, ratio))
        nearest_x = start.x() + ratio * dx
        nearest_y = start.y() + ratio * dy
        return math.hypot(point.x() - nearest_x, point.y() - nearest_y)

    def _select_annotation(self, annotation):
        self._active_annotation = annotation
        self._color = QColor(annotation["color"])
        self._refresh_color_button()
        self.width_spin.setValue(float(annotation["width"]))
        if annotation["kind"] == "text":
            self.font_size_spin.setValue(float(annotation["font_size"]))
            family = annotation.get("font_family", self.font().family())
            self.font_combo.setCurrentFont(self._font_with_family(family))
            self._set_font_family(family)

    def _move_text_annotation(self, point):
        annotation = self._moving_text
        size = annotation["size"]
        desired = self._moving_text_start + point - self._drag_start
        max_x = max(self.selection.left(), self.selection.right() - size.width() + 1)
        max_y = max(self.selection.top(), self.selection.bottom() - size.height() + 1)
        desired.setX(min(max(desired.x(), self.selection.left()), max_x))
        desired.setY(min(max(desired.y(), self.selection.top()), max_y))
        annotation["start"] = desired
        annotation["end"] = QPoint(desired)

    def _font_with_family(self, family):
        font = self.font()
        font.setFamily(family or self.font().family())
        return font

    def _apply_editor_font(self, editor):
        font = self._font_with_family(editor.property("annotationFontFamily"))
        font.setPixelSize(round(float(editor.property("annotationFontSize"))))
        font.setBold(True)
        editor.setFont(font)

    def _refresh_text_metrics(self, annotation):
        font = self._font_with_family(
            annotation.get("font_family", self.font().family())
        )
        font.setPixelSize(round(annotation["font_size"]))
        font.setBold(True)
        text_size = QFontMetrics(font).boundingRect(annotation["text"]).size()
        text_size.setWidth(text_size.width() + 6)
        text_size.setHeight(text_size.height() + 4)
        annotation["size"] = text_size

    def _commit_text(self):
        editor = self._text_editor
        if editor is None:
            return
        self._text_editor = None
        text = editor.text().strip()
        if text:
            point = editor.property("annotationPoint")
            annotation_width = float(editor.property("annotationWidth"))
            font_size = float(editor.property("annotationFontSize"))
            font_family = str(editor.property("annotationFontFamily"))
            annotation = self._active_annotation or {}
            annotation.update({
                "kind": "text",
                "start": QPoint(point),
                "end": QPoint(point),
                "color": QColor(editor.property("annotationColor")),
                "width": annotation_width,
                "font_size": font_size,
                "font_family": font_family,
                "text": text,
            })
            self._refresh_text_metrics(annotation)
            if self._editing_text_index >= 0:
                self._annotations.insert(self._editing_text_index, annotation)
            else:
                self._annotations.append(annotation)
            self._active_annotation = annotation
        else:
            self._active_annotation = None
        self._editing_text_index = -1
        editor.removeEventFilter(self)
        editor.deleteLater()
        self.setFocus(Qt.OtherFocusReason)
        self.update()

    def eventFilter(self, watched, event):
        is_locked_input = self._input_lock_installed and event.type() in (
            QEvent.Wheel,
            QEvent.NativeGesture,
            QEvent.Gesture,
            QEvent.TouchBegin,
            QEvent.TouchUpdate,
            QEvent.TouchEnd,
        )
        font_list_is_scrolling = (
            self.font_combo.view().isVisible()
            and event.type()
            in (
                QEvent.Wheel,
                QEvent.NativeGesture,
                QEvent.Gesture,
                QEvent.TouchBegin,
                QEvent.TouchUpdate,
                QEvent.TouchEnd,
            )
        )
        if (
            is_locked_input
            and not font_list_is_scrolling
            and not self._is_control_event_target(watched)
        ):
            event.accept()
            return True
        if watched is self._text_editor:
            if event.type() == QEvent.KeyPress and event.key() in (
                Qt.Key_Return, Qt.Key_Enter
            ):
                self._commit_text()
                return True
            if event.type() == QEvent.FocusOut:
                self._commit_text()
        return super().eventFilter(watched, event)

    def _is_control_event_target(self, watched):
        if not isinstance(watched, QWidget):
            return False
        roots = (self.font_combo, self.font_combo.view())
        return any(root is watched or root.isAncestorOf(watched) for root in roots)

    def _install_input_lock(self):
        if self._input_lock_installed:
            return
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
            self._input_lock_installed = True

    def _remove_input_lock(self):
        if not self._input_lock_installed:
            return
        application = QApplication.instance()
        if application is not None:
            application.removeEventFilter(self)
        self._input_lock_installed = False

    def _undo(self):
        if self._annotations:
            self._annotations.pop()
            self.update()

    def _handle_points(self):
        rect = self.selection
        return {"tl": rect.topLeft(), "t": QPoint(rect.center().x(), rect.top()),
                "tr": rect.topRight(), "r": QPoint(rect.right(), rect.center().y()),
                "br": rect.bottomRight(), "b": QPoint(rect.center().x(), rect.bottom()),
                "bl": rect.bottomLeft(), "l": QPoint(rect.left(), rect.center().y())}

    def _hit_handle(self, point):
        for name, handle_point in self._handle_points().items():
            if (point - handle_point).manhattanLength() <= 10:
                return name
        return ""

    def _refresh_hover_cursor(self, point):
        handle = self._hit_handle(point) if self.selection.isValid() else ""
        cursor_map = {
            "tl": Qt.SizeFDiagCursor,
            "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor,
            "bl": Qt.SizeBDiagCursor,
            "t": Qt.SizeVerCursor,
            "b": Qt.SizeVerCursor,
            "l": Qt.SizeHorCursor,
            "r": Qt.SizeHorCursor,
        }
        if handle:
            self.setCursor(cursor_map[handle])
        elif self._text_at(point) is not None or (
            self.selection.contains(point) and not self._tool
        ):
            self.setCursor(Qt.SizeAllCursor)
        else:
            self._refresh_cursor()

    def _window_at(self, point):
        for window_rect in self._window_candidates:
            if window_rect.contains(point):
                return QRect(window_rect)
        # A point not covered by a visible window belongs to the desktop.
        # Treat that desktop area as the containing screen, matching the
        # familiar click-wallpaper-to-select-full-screen capture behavior.
        return self._screen_at(point)

    def _screen_at(self, point):
        for screen_rect in self._screen_candidates:
            if screen_rect.contains(point):
                return QRect(screen_rect)
        return QRect()

    @staticmethod
    def _macos_dock_regions(geometry, available):
        """Infer a visible bottom/side Dock from the system work area."""
        regions = []
        if available.bottom() < geometry.bottom():
            regions.append(QRect(
                geometry.left(), available.bottom() + 1, geometry.width(),
                geometry.bottom() - available.bottom(),
            ))
        if available.left() > geometry.left():
            regions.append(QRect(
                geometry.left(), geometry.top(),
                available.left() - geometry.left(), geometry.height(),
            ))
        if available.right() < geometry.right():
            regions.append(QRect(
                available.right() + 1, geometry.top(),
                geometry.right() - available.right(), geometry.height(),
            ))
        return [region for region in regions if region.width() >= 12 and region.height() >= 12]

    @staticmethod
    def _unique_regions(regions):
        result = []
        seen = set()
        for region in regions:
            values = (region.x(), region.y(), region.width(), region.height())
            if values not in seen:
                seen.add(values)
                result.append(QRect(region))
        return result

    def _translate_annotations(self, delta):
        if delta.isNull():
            return
        for annotation in self._annotations:
            annotation["start"] += delta
            annotation["end"] += delta
            if "points" in annotation:
                annotation["points"] = [point + delta for point in annotation["points"]]

    def _resize_selection(self, point):
        rect = QRect(self._selection_start)
        if "l" in self._handle:
            rect.setLeft(point.x())
        if "r" in self._handle:
            rect.setRight(point.x())
        if "t" in self._handle:
            rect.setTop(point.y())
        if "b" in self._handle:
            rect.setBottom(point.y())
        self.selection = rect.normalized().intersected(self.rect())

    def _position_toolbar(self):
        self.toolbar.resize(self.toolbar.sizeHint().width(), self.TOOLBAR_HEIGHT)
        self._center_toolbar_buttons()
        x = min(max(8, self.selection.right() - self.toolbar.width()), self.width() - self.toolbar.width() - 8)
        y = self.selection.bottom() + 10
        if y + self.toolbar.height() > self.height() - 8:
            y = self.selection.top() - self.toolbar.height() - 10
        self.toolbar.move(x, max(8, y))

    def _center_toolbar_buttons(self):
        for button in self.toolbar.findChildren(
            QPushButton, options=Qt.FindDirectChildrenOnly
        ):
            button.move(button.x(), (self.toolbar.height() - button.height()) // 2)

    def _render_selection(self):
        if not self.selection.isValid():
            return QPixmap()
        result = QPixmap(self._selection_pixel_size())
        result.setDevicePixelRatio(self._dpr)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.drawPixmap(QRectF(QRect(QPoint(), self.selection.size())), self._desktop, QRectF(
            self.selection.x() * self._dpr, self.selection.y() * self._dpr,
            self.selection.width() * self._dpr, self.selection.height() * self._dpr))
        painter.translate(-self.selection.topLeft())
        painter.setClipRect(self.selection)
        for annotation in self._annotations:
            self._paint_annotation(painter, annotation)
        painter.end()
        return result

    def _selection_pixel_size(self):
        return QSize(
            round(self.selection.width() * self._dpr),
            round(self.selection.height() * self._dpr),
        )

    def _copy_and_finish(self):
        self._commit_text()
        pixmap = self._render_selection()
        if pixmap.isNull():
            return
        QGuiApplication.clipboard().setPixmap(pixmap)
        self._closing = True
        self._remove_input_lock()
        self.hide()
        self.completed.emit()

    def _save(self):
        self._commit_text()
        pixmap = self._render_selection()
        if pixmap.isNull():
            return
        if self._save_dialog is not None:
            self._save_dialog.raise_()
            self._save_dialog.activateWindow()
            return
        dialog = QFileDialog(self, "保存截图")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setNameFilter("PNG 图片 (*.png)")
        pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        directory = Path(pictures) if pictures else Path.home()
        dialog.setDirectory(str(directory))
        local_now = datetime.now().astimezone()
        dialog.selectFile(f"截图_{local_now:%Y-%m-%d_%H%M%S}.png")
        dialog.setDefaultSuffix("png")
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dialog.fileSelected.connect(lambda path: self._save_to_path(pixmap, path))
        dialog.finished.connect(self._save_dialog_closed)
        self._save_dialog = dialog
        dialog.open()
        _raise_window_level(dialog)
        dialog.raise_()
        dialog.activateWindow()

    def _save_to_path(self, pixmap, path):
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            try:
                saved = pixmap.save(path, "PNG")
            except (OSError, RuntimeError):
                saved = False
            if not saved:
                QMessageBox.critical(
                    self,
                    "保存失败",
                    "无法保存截图，请检查保存位置是否可写后重试。",
                )
                return
            self._closing = True
            self._remove_input_lock()
            self.hide()
            self.completed.emit()

    def _save_dialog_closed(self):
        dialog = self._save_dialog
        self._save_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    def _cancel(self):
        if self._closing:
            return
        self._closing = True
        self._hide_popups()
        if self._color_dialog is not None:
            self._color_dialog.reject()
        if self._save_dialog is not None:
            self._save_dialog.reject()
        if self._text_editor is not None:
            editor = self._text_editor
            self._text_editor = None
            editor.removeEventFilter(self)
            editor.deleteLater()
        self._current = None
        self._drag_mode = ""
        self._remove_input_lock()
        self.hide()
        self.cancelled.emit()
