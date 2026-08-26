"""Full-desktop screenshot selection and annotation overlay."""

from __future__ import annotations

import platform
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
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QColorDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from fuzztoolbox.tools.color_picker.eyedropper import _grab_screen, _raise_window_level
from fuzztoolbox.ui.style_loader import apply_style

from .annotations import (
    annotation_bounds,
    annotation_contains,
    append_brush_points,
    new_annotation,
    text_rect,
    translate_annotations,
)
from .capture_backend import (
    ScreenCaptureCoordinator,
    compose_desktop,
    virtual_geometry,
)
from .controls import ScreenshotScrollBar, SelectionOptionsBar
from .renderer import AnnotationRenderer
from .selection import (
    handle_points,
    hit_handle,
    macos_dock_regions,
    move_selection,
    resize_selection,
    unique_regions,
)
from .toolbar import ScreenshotToolbar
from .window_detection import enumerate_window_rects

__all__ = ["ScreenshotOverlay", "ScreenshotScrollBar"]


class ScreenshotOverlay(QWidget):
    completed = Signal()
    cancelled = Signal()
    capture_ready = Signal()

    TOOLS = (("矩形", "rect"), ("椭圆", "ellipse"), ("箭头", "arrow"),
             ("画笔", "pen"), ("文字", "text"), ("马赛克", "mosaic"))
    COLORS = (QColor("#ff4d4f"), QColor("#409eff"), QColor("#19be6b"),
              QColor("#ffd43b"), QColor("#ffffff"), QColor("#202124"))
    CORNER_RADIUS_MAXIMUM = 100
    SHADOW_PADDING = 18
    SHADOW_OFFSET_Y = 3
    SHADOW_BLUR_RADIUS = 14
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
        self._renderer = AnnotationRenderer(
            self._desktop,
            QRect(),
            self._dpr,
            self.font().family(),
        )
        self.selection = QRect()
        self._drag_start = QPoint()
        self._drag_mode = ""
        self._handle = ""
        self._selection_start = QRect()
        self._annotations = []
        self._annotation_layer = QPixmap()
        self._annotation_layer_dirty = True
        self._current = None
        self._tool = ""
        self._color_index = 0
        self._color = QColor(self.COLORS[self._color_index])
        self._width = 4
        self._font_size = 20
        self._font_family = self.font().family()
        self._corner_radius = 0
        self._shadow_enabled = False
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
        self._capture = ScreenCaptureCoordinator(_grab_screen, self)
        self._capture.ready.connect(self._show_overlay)
        self._capture.failed.connect(self.cancelled.emit)
        self.toolbar = ScreenshotToolbar(
            self,
            tools=self.TOOLS,
            color=self._color,
            width=self._width,
            font_size=self._font_size,
            font=self.font(),
        )
        self.toolbar.tool_changed.connect(self._select_tool)
        self.toolbar.color_changed.connect(self._choose_color)
        self.toolbar.custom_color_requested.connect(self._choose_custom_color)
        self.toolbar.width_changed.connect(self._set_width)
        self.toolbar.font_size_changed.connect(self._set_font_size)
        self.toolbar.font_family_changed.connect(self._set_font_family)
        self.toolbar.undo_requested.connect(self._undo)
        self.toolbar.save_requested.connect(self._save)
        self.toolbar.finish_requested.connect(self._copy_and_finish)
        self.toolbar.cancel_requested.connect(self._cancel)
        self.selection_options = SelectionOptionsBar(self)
        self.selection_options.radius_changed.connect(self._set_corner_radius)
        self.selection_options.shadow_toggled.connect(self._set_shadow_enabled)
        self.selection_options.hide()
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._escape_shortcut.setContext(Qt.ApplicationShortcut)
        self._escape_shortcut.activated.connect(self._cancel)

    def begin(self):
        screens = QGuiApplication.screens()
        if not screens:
            self.cancelled.emit()
            return
        self._virtual = virtual_geometry(screens)
        self._capture.capture(screens)

    def _show_overlay(self, shots):
        self._closing = False
        self._install_input_lock()
        self._shots = shots
        self._desktop, self._dpr = compose_desktop(shots, self._virtual)
        self._corner_radius = 0
        self._shadow_enabled = False
        self.selection_options.hide()
        self._invalidate_annotation_layer()
        self._renderer.update_context(
            self._desktop,
            self.selection,
            self._dpr,
            self.font().family(),
        )
        # The frozen desktop no longer depends on the live window server.  The
        # launcher may stop its macOS order-out watchdog at this exact point.
        self.capture_ready.emit()
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
                dock_fallbacks.extend(macos_dock_regions(geometry, available))
        self._window_candidates = unique_regions(
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.drawPixmap(QPoint(), self._desktop)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 112))
        if self.selection.isValid() and self.selection.width() > 1:
            selection_path = self._selection_path()
            if self._shadow_enabled:
                self._paint_soft_shadow(
                    painter,
                    QRectF(self.selection),
                    self._effective_corner_radius(QRectF(self.selection)),
                )
            painter.save()
            painter.setClipPath(selection_path)
            painter.drawPixmap(QRectF(self.selection), self._desktop, QRectF(
                self.selection.x() * self._dpr,
                self.selection.y() * self._dpr,
                self.selection.width() * self._dpr,
                self.selection.height() * self._dpr,
            ))
            painter.drawPixmap(
                self.selection.topLeft(),
                self._committed_annotation_layer(),
            )
            if self._current and annotation_bounds(self._current).intersects(
                event.rect()
            ):
                if self._current["kind"] == "mosaic":
                    self._paint_annotation(
                        painter,
                        self._current,
                        mosaic_source=self._committed_annotation_layer(),
                        mosaic_source_rect=self.selection,
                    )
                else:
                    self._paint_annotation(painter, self._current)
            painter.restore()
            painter.setPen(QPen(QColor("#55b6ff"), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(selection_path)
            if not self._selection_is_locked():
                self._paint_handles(painter)
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

    def _paint_annotation(self, painter, annotation, **options):
        self._annotation_renderer().paint(painter, annotation, **options)

    def _committed_annotation_layer(self):
        pixel_size = self._selection_pixel_size()
        if (
            not self._annotation_layer_dirty
            and not self._annotation_layer.isNull()
            and self._annotation_layer.size() == pixel_size
        ):
            return self._annotation_layer
        layer = QPixmap(pixel_size)
        layer.setDevicePixelRatio(self._dpr)
        layer.fill(Qt.transparent)
        painter = QPainter(layer)
        painter.drawPixmap(
            QRectF(QRect(QPoint(), self.selection.size())),
            self._desktop,
            QRectF(
                self.selection.x() * self._dpr,
                self.selection.y() * self._dpr,
                self.selection.width() * self._dpr,
                self.selection.height() * self._dpr,
            ),
        )
        self._prepare_annotation_layer_painter(painter)
        for annotation in self._annotations:
            if annotation["kind"] == "mosaic":
                painter.end()
                source = layer.copy()
                painter = QPainter(layer)
                self._prepare_annotation_layer_painter(painter)
                self._paint_annotation(
                    painter,
                    annotation,
                    mosaic_source=source,
                    mosaic_source_rect=self.selection,
                )
            else:
                self._paint_annotation(painter, annotation)
        painter.end()
        self._annotation_layer = layer
        self._annotation_layer_dirty = False
        return self._annotation_layer

    def _invalidate_annotation_layer(self):
        self._annotation_layer_dirty = True

    def _prepare_annotation_layer_painter(self, painter):
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(-self.selection.topLeft())
        painter.setClipRect(self.selection)

    def _annotation_renderer(self):
        self._renderer.update_context(
            self._desktop,
            self.selection,
            self._dpr,
            self.font().family(),
        )
        return self._renderer

    def _paint_handles(self, painter):
        painter.setPen(QPen(Qt.white, 1))
        painter.setBrush(QColor("#55b6ff"))
        for point in handle_points(self.selection).values():
            painter.drawRect(QRect(point.x() - 4, point.y() - 4, 8, 8))

    def _selection_path(self, *, local=False):
        rect = (
            QRectF(QRect(QPoint(), self.selection.size()))
            if local
            else QRectF(self.selection)
        )
        path = QPainterPath()
        radius = self._effective_corner_radius(rect)
        if radius > 0:
            path.addRoundedRect(rect, radius, radius)
        else:
            path.addRect(rect)
        return path

    def _set_corner_radius(self, value):
        self._corner_radius = min(
            max(0, int(value)),
            self.CORNER_RADIUS_MAXIMUM,
        )
        if self.selection_options.radius_slider.value() != self._corner_radius:
            self.selection_options.radius_slider.setValue(self._corner_radius)
        self.update(self._selection_dirty_region(self.selection))

    def _set_shadow_enabled(self, enabled):
        self._shadow_enabled = bool(enabled)
        if self.selection_options.shadow_checkbox.isChecked() != self._shadow_enabled:
            self.selection_options.shadow_checkbox.setChecked(self._shadow_enabled)
        self.update(self._selection_dirty_region(self.selection))

    def _effective_corner_radius(self, rect):
        return min(
            float(self._corner_radius),
            rect.width() / 2.0,
            rect.height() / 2.0,
        )

    def _paint_soft_shadow(self, painter, rect, corner_radius):
        """Paint a lightweight soft shadow without a temporary scene/effect."""
        shadow_rect = QRectF(rect).translated(0, self.SHADOW_OFFSET_Y)
        painter.save()
        painter.setPen(Qt.NoPen)
        for spread in range(self.SHADOW_BLUR_RADIUS, 0, -1):
            opacity = 4 + round(9 * (1.0 - spread / self.SHADOW_BLUR_RADIUS))
            painter.setBrush(QColor(0, 0, 0, opacity))
            expanded = shadow_rect.adjusted(-spread, -spread, spread, spread)
            radius = corner_radius + spread
            painter.drawRoundedRect(expanded, radius, radius)
        painter.restore()

    def _sync_selection_options(self):
        if self.selection.width() < 8 or self.selection.height() < 8:
            self.selection_options.hide()
            return
        self.selection_options.set_selection(
            self._selection_pixel_size(),
            self._corner_radius,
            self._shadow_enabled,
        )
        bar = self.selection_options
        x = min(
            max(8, self.selection.left()),
            max(8, self.width() - bar.width() - 8),
        )
        y = self.selection.top() - bar.height() - 7
        if y < 8:
            y = self.selection.top() + 7
        bar.move(x, y)
        bar.show()
        bar.raise_()

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
        locked = self._selection_is_locked()
        handle = hit_handle(self.selection, point) if not locked else ""
        if handle:
            self._drag_mode = "resize"
            self._handle = handle
            self._selection_start = QRect(self.selection)
            return
        if self._tool and self._tool != "text" and self.selection.contains(point):
            self._drag_mode = "draw_pending"
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
            self._current = new_annotation(
                self._tool,
                point,
                point,
                self._color,
                self._width,
            )
            return
        if locked:
            return
        if self.selection.contains(point):
            self._drag_mode = "move"
            self._selection_start = QRect(self.selection)
        else:
            self._annotations.clear()
            self._renderer.retain_annotations(self._annotations)
            self._invalidate_annotation_layer()
            self.selection = QRect(point, point)
            self._drag_mode = "select"
            self.toolbar.hide()

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        self._cursor_pos = point
        old_annotation_region = self._active_draw_region()
        old_selection_region = self._selection_dirty_region(self.selection)
        if not self.selection.isValid() and not self._drag_mode:
            self._hovered_window = self._window_at(point)
        if self._drag_mode == "window_pending":
            if (point - self._drag_start).manhattanLength() > 4:
                self._drag_mode = "select"
                self._pending_window = QRect()
                self.selection = QRect(self._drag_start, point).normalized().intersected(
                    self.rect()
                )
        elif self._drag_mode == "draw_pending":
            if (point - self._drag_start).manhattanLength() > 4:
                self._active_annotation = None
                self._drag_mode = "annotate"
                self._current = new_annotation(
                    self._tool,
                    self._drag_start,
                    point,
                    self._color,
                    self._width,
                )
                if self._current["kind"] in ("pen", "mosaic"):
                    append_brush_points(self._current, point)
        elif self._drag_mode == "select":
            self.selection = QRect(self._drag_start, point).normalized().intersected(self.rect())
        elif self._drag_mode == "move":
            self.selection = move_selection(
                self._selection_start,
                point - self._drag_start,
                self.rect(),
            )
        elif self._drag_mode == "resize":
            self.selection = resize_selection(
                self._selection_start,
                self._handle,
                point,
                self.rect(),
            )
        elif self._drag_mode == "move_text" and self._moving_text is not None:
            self._move_text_annotation(point)
        elif self._drag_mode == "annotate" and self._current:
            self._current["end"] = point
            if self._current["kind"] in ("pen", "mosaic"):
                append_brush_points(self._current, point)
        elif not self._drag_mode:
            self._refresh_hover_cursor(point)
        if self._drag_mode in ("move", "resize", "select", "window_pending"):
            self._sync_selection_options()
            new_selection_region = self._selection_dirty_region(self.selection)
            self.update(old_selection_region.united(new_selection_region))
        elif self._drag_mode in ("annotate", "move_text"):
            new_annotation_region = self._active_draw_region()
            dirty = old_annotation_region.united(new_annotation_region)
            if dirty.isValid():
                self.update(dirty.intersected(self.rect()))
            else:
                self.update()
        else:
            self.update()

    @staticmethod
    def _selection_dirty_region(selection):
        if not selection.isValid():
            return QRect()
        right_padding = max(24, 128 - selection.width())
        return selection.adjusted(-24, -42, right_padding, 24)

    def _active_draw_region(self):
        if self._drag_mode == "annotate" and self._current is not None:
            return annotation_bounds(self._current)
        if self._drag_mode == "move_text" and self._moving_text is not None:
            return annotation_bounds(self._moving_text)
        return QRect()

    def _selection_is_locked(self):
        return bool(self._annotations) or self._text_editor is not None

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._drag_mode == "window_pending":
            self.selection = QRect(self._pending_window)
            self._pending_window = QRect()
            self._hovered_window = QRect()
        if self._drag_mode == "draw_pending":
            annotation = self._annotation_at(event.position().toPoint())
            if annotation is not None:
                self._select_annotation(annotation)
            else:
                self._annotations.append(
                    new_annotation(
                        self._tool,
                        self._drag_start,
                        self._drag_start,
                        self._color,
                        self._width,
                    )
                )
                self._renderer.retain_annotations(self._annotations)
                self._invalidate_annotation_layer()
        if self._drag_mode == "annotate" and self._current:
            self._annotations.append(self._current)
            self._current = None
            self._renderer.retain_annotations(self._annotations)
            self._invalidate_annotation_layer()
        if self._drag_mode == "move":
            delta = self.selection.topLeft() - self._selection_start.topLeft()
            translate_annotations(self._annotations, delta)
        if self.selection.width() >= 8 and self.selection.height() >= 8:
            self._position_toolbar()
            self.toolbar.show()
            self._sync_selection_options()
        else:
            self.selection = QRect()
            self.toolbar.hide()
            self.selection_options.hide()
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
        elif event.key() == Qt.Key_Space and not self._selection_is_locked():
            screen = self._screen_at(self._cursor_pos)
            if screen.isValid():
                self.selection = screen
                self._hovered_window = QRect()
                self._position_toolbar()
                self.toolbar.show()
                self._sync_selection_options()
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

    def _select_tool(self, tool, checked=True):
        self._commit_text()
        self.toolbar.set_active_tool(tool, checked)
        if checked:
            self._tool = tool
        else:
            self._tool = ""
        self._refresh_cursor()

    def _choose_color(self, color):
        self._color = QColor(color)
        if self._active_annotation is not None:
            self._active_annotation["color"] = QColor(self._color)
            self._invalidate_annotation_layer()
            if self._text_editor is not None:
                self._text_editor.setProperty("annotationColor", self._color)
            self.update()
        self.toolbar.set_color(self._color)

    def _choose_custom_color(self):
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

    def _set_width(self, value):
        self._width = float(value)
        if self._active_annotation is not None:
            self._active_annotation["width"] = self._width
            self._invalidate_annotation_layer()
            if self._text_editor is not None:
                self._text_editor.setProperty("annotationWidth", self._width)
            self.update()
        self._refresh_cursor()

    def _set_font_size(self, value):
        self._font_size = float(value)
        if self._text_editor is not None:
            self._text_editor.setProperty("annotationFontSize", self._font_size)
            self._apply_editor_font(self._text_editor)
        if (
            self._active_annotation is not None
            and self._active_annotation["kind"] == "text"
        ):
            self._active_annotation["font_size"] = self._font_size
            self._refresh_text_metrics(self._active_annotation)
            self._invalidate_annotation_layer()
            self.update()

    def _set_font_family(self, family):
        self._font_family = family or self.font().family()
        if self._text_editor is not None:
            self._text_editor.setProperty("annotationFontFamily", self._font_family)
            self._apply_editor_font(self._text_editor)
        if (
            self._active_annotation is not None
            and self._active_annotation["kind"] == "text"
        ):
            self._active_annotation["font_family"] = self._font_family
            self._refresh_text_metrics(self._active_annotation)
            self._invalidate_annotation_layer()
            self.update()

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

    def _hide_popups(self):
        self.toolbar.hide_popups()

    def _begin_text_edit(self, point, *, annotation=None):
        self._commit_text()
        text = ""
        if annotation is not None:
            self._editing_text_index = self._annotations.index(annotation)
            self._annotations.pop(self._editing_text_index)
            self._invalidate_annotation_layer()
            self._active_annotation = annotation
            point = QPoint(annotation["start"])
            text = annotation["text"]
            self._color = QColor(annotation["color"])
            self._width = float(annotation["width"])
            self.toolbar.set_width(self._width)
            self.toolbar.set_font_size(float(annotation["font_size"]))
            family = annotation.get("font_family", self.font().family())
            self.toolbar.set_font_family(family)
            self.toolbar.set_color(self._color)
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

    def _text_at(self, point):
        for annotation in reversed(self._annotations):
            if annotation["kind"] == "text" and text_rect(annotation).contains(
                point
            ):
                return annotation
        return None

    def _annotation_at(self, point):
        for annotation in reversed(self._annotations):
            if annotation_contains(annotation, point):
                return annotation
        return None

    def _select_annotation(self, annotation):
        self._active_annotation = annotation
        self._color = QColor(annotation["color"])
        self.toolbar.set_color(self._color)
        self.toolbar.set_width(float(annotation["width"]))
        if annotation["kind"] == "text":
            self.toolbar.set_font_size(float(annotation["font_size"]))
            family = annotation.get("font_family", self.font().family())
            self.toolbar.set_font_family(family)

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
        self._invalidate_annotation_layer()

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
            self._invalidate_annotation_layer()
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
        font_list_is_scrolling = self.toolbar.font_list_is_scrolling(event.type())
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
        return (
            watched is self.selection_options
            or self.selection_options.isAncestorOf(watched)
            or self.toolbar.is_control_event_target(watched)
        )

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
            self._renderer.retain_annotations(self._annotations)
            self._invalidate_annotation_layer()
            self.update()

    def _refresh_hover_cursor(self, point):
        locked = self._selection_is_locked()
        handle = (
            hit_handle(self.selection, point)
            if self.selection.isValid() and not locked
            else ""
        )
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
        elif self._text_at(point) is not None:
            self.setCursor(Qt.SizeAllCursor)
        elif locked:
            if self._tool:
                self._refresh_cursor()
            else:
                self.setCursor(Qt.ArrowCursor)
        elif self.selection.contains(point) and not self._tool:
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

    def _position_toolbar(self):
        self.toolbar.position_for(self.selection, self.rect())

    def _render_selection(self):
        if not self.selection.isValid():
            return QPixmap()
        capture = QPixmap(self._selection_pixel_size())
        capture.setDevicePixelRatio(self._dpr)
        capture.fill(Qt.transparent)
        painter = QPainter(capture)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setClipPath(self._selection_path(local=True))
        painter.drawPixmap(QRectF(QRect(QPoint(), self.selection.size())), self._desktop, QRectF(
            self.selection.x() * self._dpr, self.selection.y() * self._dpr,
            self.selection.width() * self._dpr, self.selection.height() * self._dpr))
        painter.drawPixmap(QPoint(), self._committed_annotation_layer())
        painter.end()

        if not self._shadow_enabled:
            return capture

        padding = self.SHADOW_PADDING
        logical_size = self.selection.size() + QSize(padding * 2, padding * 2)
        result = QPixmap(
            round(logical_size.width() * self._dpr),
            round(logical_size.height() * self._dpr),
        )
        result.setDevicePixelRatio(self._dpr)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing, True)
        target = QRectF(
            padding,
            padding,
            self.selection.width(),
            self.selection.height(),
        )
        self._paint_soft_shadow(
            painter,
            target,
            self._effective_corner_radius(target),
        )
        painter.drawPixmap(QPoint(padding, padding), capture)
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
        self.selection_options.hide()
        self._remove_input_lock()
        self.hide()
        self.cancelled.emit()

    def cancel(self) -> None:
        """Cancel the active capture through the normal completion path."""
        self._cancel()
