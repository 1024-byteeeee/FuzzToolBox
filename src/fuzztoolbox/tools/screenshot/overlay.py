"""Full-desktop screenshot selection and annotation overlay."""

from __future__ import annotations

import copy
import math
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
    QBitmap,
    QColor,
    QCursor,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QShortcut,
    QTransform,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QColorDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QWidget,
)

from fuzztoolbox.tools.color_picker.eyedropper import _grab_screen, _raise_window_level
from fuzztoolbox.ui.style_loader import apply_style

from .annotations import (
    annotation_bounds,
    annotation_contains,
    annotation_geometry,
    append_brush_points,
    new_annotation,
    resize_annotation,
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
             ("画笔", "pen"), ("文字", "text"), ("马赛克", "mosaic"),
             ("橡皮擦", "eraser"))
    COLORS = (QColor("#ff4d4f"), QColor("#409eff"), QColor("#19be6b"),
              QColor("#ffd43b"), QColor("#ffffff"), QColor("#202124"))
    CORNER_RADIUS_MAXIMUM = 100
    SHADOW_PADDING = 18
    SHADOW_OFFSET_Y = 3
    SHADOW_BLUR_RADIUS = 14
    RASTER_TILE_SIZE = 256
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
        self._undo_stack = []
        self._gesture_geometry_before = QRect()
        self._annotation_layer = QPixmap()
        self._annotation_layer_selection = QRect()
        self._annotation_layer_dirty = True
        self._annotation_composite_cache = QPixmap()
        self._annotation_composite_key = None
        self._current_stroke_tiles = None
        self._current_stroke_point_count = 0
        self._current_stroke_dirty = QRect()
        self._pen_preview_cache = None
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
        self._element_start = None
        self._element_bounds_start = QRect()
        self._drag_preview_annotation = None
        self._drag_preview_offset = QPoint()
        self._drag_preview_region = None
        self._drag_preview_bounds = QRect()
        self._resize_preview_bounds = QRect()
        self._drag_preview_layer = QPixmap()
        self._drag_preview_tiles = []
        self._drag_base_layer = QPixmap()
        self._drag_scene_layer = QPixmap()
        self._drag_foreground_layer = QPixmap()
        self._drag_suffix_annotations = []
        self._drag_dynamic_scene_layer = QPixmap()
        self._drag_dynamic_scene_key = None
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
        self._discard_pen_preview_cache()
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
        fast_drag_scene = (
            self.selection.isValid()
            and self.selection.width() > 1
            and self._has_drag_preview()
            and not self._drag_scene_layer.isNull()
            and self._corner_radius == 0
            and not self._shadow_enabled
        )
        painter.save()
        if fast_drag_scene:
            painter.setClipRegion(
                event.region().subtracted(QRegion(self.selection)),
                Qt.IntersectClip,
            )
        painter.drawPixmap(QPoint(), self._desktop)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 112))
        painter.restore()
        if self.selection.isValid() and self.selection.width() > 1:
            selection_path = self._selection_path()
            if self._shadow_enabled:
                self._paint_soft_shadow(
                    painter,
                    QRectF(self.selection),
                    self._effective_corner_radius(QRectF(self.selection)),
                )
            painter.save()
            # Re-apply the paint-event region explicitly before the selection
            # path. QPainter's path clipping otherwise expands a fragmented
            # QRegion to its bounding rectangle on the widget paint device.
            painter.setClipRegion(event.region(), Qt.IntersectClip)
            painter.setClipPath(selection_path, Qt.IntersectClip)
            if self._has_drag_preview():
                if not fast_drag_scene:
                    self._paint_selection_desktop(painter)
                dynamic_scene = self._dynamic_drag_scene()
                scene = (
                    dynamic_scene
                    if not dynamic_scene.isNull()
                    else (
                        self._drag_scene_layer
                        if not self._drag_scene_layer.isNull()
                        else self._drag_base_layer
                    )
                )
                painter.drawPixmap(self.selection.topLeft(), scene)
                if dynamic_scene.isNull():
                    self._paint_drag_preview(painter, event.region())
                    if not self._drag_foreground_layer.isNull():
                        painter.drawPixmap(
                            self.selection.topLeft(), self._drag_foreground_layer
                        )
            else:
                self._paint_selection_desktop(painter)
                painter.drawPixmap(
                    self.selection.topLeft(), self._committed_annotation_layer()
                )
            if (
                not self._has_drag_preview()
                and self._current
                and annotation_bounds(self._current).intersects(event.rect())
            ):
                if self._has_current_stroke_cache():
                    self._paint_current_stroke(painter, event.region())
                elif self._current["kind"] == "mosaic":
                    self._paint_annotation(
                        painter,
                        self._current,
                        mosaic_source=self._annotation_composite(
                            self._committed_annotation_layer()
                        ),
                        mosaic_source_rect=self.selection,
                    )
                elif self._current["kind"] == "eraser":
                    self._paint_annotation(
                        painter,
                        self._current,
                        eraser_source=self._desktop,
                        eraser_source_rect=QRectF(
                            0,
                            0,
                            self._desktop.width() / max(0.01, self._dpr),
                            self._desktop.height() / max(0.01, self._dpr),
                        ),
                    )
                else:
                    self._paint_annotation(painter, self._current)
            painter.restore()
            painter.setPen(QPen(QColor("#55b6ff"), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(selection_path)
            if not self._selection_is_locked():
                self._paint_handles(painter)
            if self._active_annotation in self._annotations:
                self._paint_annotation_handles(painter)
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

    def _paint_selection_desktop(self, painter):
        painter.drawPixmap(
            QRectF(self.selection),
            self._desktop,
            QRectF(
                self.selection.x() * self._dpr,
                self.selection.y() * self._dpr,
                self.selection.width() * self._dpr,
                self.selection.height() * self._dpr,
            ),
        )

    def _paint_annotation(self, painter, annotation, **options):
        self._annotation_renderer().paint(painter, annotation, **options)

    def _paint_drag_preview(self, painter, exposed):
        """Blit cached tiles without rebuilding the element's vector path."""
        if self._drag_mode == "resize_element" and self._resize_preview_bounds.isValid():
            transform = self._resize_preview_transform()
            if transform is None:
                return
            painter.save()
            painter.setTransform(transform, True)
            for bounds, tile in self._drag_preview_tiles:
                painter.drawPixmap(bounds.topLeft(), tile)
            painter.restore()
            return
        for bounds, tile in self._drag_preview_tiles:
            target = bounds.translated(self._drag_preview_offset)
            if exposed.intersects(target):
                painter.drawPixmap(target.topLeft(), tile)

    def _paint_current_stroke(self, painter, exposed):
        """Blit only exposed tiles of the pen stroke in progress."""
        for bounds, tile in (self._current_stroke_tiles or {}).values():
            if exposed.intersects(bounds):
                painter.drawPixmap(bounds.topLeft(), tile)

    def _dynamic_drag_scene(self):
        """Compose a suffix containing mosaic against the moving cached item."""
        if (
            not self._drag_suffix_annotations
            or self._drag_scene_layer.isNull()
            or not self._drag_intersects_suffix_mosaic()
        ):
            return QPixmap()
        target = self._resize_preview_bounds
        key = (
            self._drag_mode,
            self._drag_preview_offset.x(),
            self._drag_preview_offset.y(),
            target.x(),
            target.y(),
            target.width(),
            target.height(),
        )
        if (
            self._drag_dynamic_scene_key == key
            and not self._drag_dynamic_scene_layer.isNull()
        ):
            return self._drag_dynamic_scene_layer
        layer = QPixmap(self._drag_scene_layer)
        painter = QPainter(layer)
        self._prepare_annotation_layer_painter(painter)
        self._paint_drag_preview(painter, QRegion(self.selection))
        painter.end()
        for annotation in self._drag_suffix_annotations:
            source = None
            source_rect = None
            if annotation["kind"] == "mosaic":
                source, source_rect = self._mosaic_source_crop(
                    QPixmap(layer), annotation
                )
            painter = QPainter(layer)
            self._prepare_annotation_layer_painter(painter)
            if annotation["kind"] == "mosaic":
                self._paint_annotation(
                    painter,
                    annotation,
                    mosaic_source=source,
                    mosaic_source_rect=source_rect,
                )
            else:
                self._paint_annotation(painter, annotation)
            painter.end()
        self._drag_dynamic_scene_layer = layer
        self._drag_dynamic_scene_key = key
        return self._drag_dynamic_scene_layer

    def _drag_intersects_suffix_mosaic(self):
        return not self._drag_dependent_suffix_region().isEmpty()

    def _drag_source_change_region(self):
        """Return source pixels changed by the cached active annotation."""
        if not self._has_drag_preview() or self._drag_preview_region is None:
            return QRegion()
        affected = QRegion(self._drag_preview_region)
        if self._drag_mode == "resize_element":
            transform = self._resize_preview_transform()
            if transform is not None:
                for preview_bounds in self._drag_preview_region:
                    affected = affected.united(
                        QRegion(
                            transform.mapRect(QRectF(preview_bounds))
                            .toAlignedRect()
                            .adjusted(-2, -2, 2, 2)
                        )
                    )
        else:
            affected = affected.united(
                self._drag_preview_region.translated(self._drag_preview_offset)
            )
        return affected.intersected(QRegion(self.selection))

    def _mosaic_dependency_blocks(self, region):
        """Expand changed source pixels to every sampled mosaic block."""
        block = AnnotationRenderer.MOSAIC_BLOCK_SIZE
        expanded = QRegion()
        for bounds in region:
            # Smooth downsampling can sample across the immediate block edge.
            # One neighbouring block is a conservative, still-local margin.
            bounds = bounds.adjusted(-block, -block, block, block)
            left = self.selection.left() + math.floor(
                (bounds.left() - self.selection.left()) / block
            ) * block
            top = self.selection.top() + math.floor(
                (bounds.top() - self.selection.top()) / block
            ) * block
            right = self.selection.left() + math.ceil(
                (bounds.right() + 1 - self.selection.left()) / block
            ) * block
            bottom = self.selection.top() + math.ceil(
                (bounds.bottom() + 1 - self.selection.top()) / block
            ) * block
            expanded = expanded.united(
                QRegion(QRect(left, top, right - left, bottom - top))
            )
        return expanded.intersected(QRegion(self.selection))

    def _drag_dependent_suffix_region(self):
        """Propagate active-item damage through later mosaic annotations."""
        if not self._drag_suffix_annotations:
            return QRegion()
        changed = self._drag_source_change_region()
        damage = QRegion()
        for annotation in self._drag_suffix_annotations:
            if annotation["kind"] != "mosaic":
                continue
            dependent = self._mosaic_dependency_blocks(changed).intersected(
                QRegion(annotation_bounds(annotation))
            )
            if dependent.isEmpty():
                continue
            damage = damage.united(dependent)
            # A changed mosaic becomes part of the source sampled by every
            # later mosaic, so dependency propagation must continue in order.
            changed = changed.united(dependent)
        return damage.intersected(QRegion(self.rect()))

    def _mosaic_source_crop(self, source, annotation):
        bounds = annotation_bounds(annotation).intersected(self.selection)
        if source.isNull() or not bounds.isValid():
            return source, QRect(self.selection)
        block = AnnotationRenderer.MOSAIC_BLOCK_SIZE
        left = self.selection.left() + (
            (bounds.left() - self.selection.left()) // block
        ) * block
        top = self.selection.top() + (
            (bounds.top() - self.selection.top()) // block
        ) * block
        right = self.selection.left() + math.ceil(
            (bounds.right() + 1 - self.selection.left()) / block
        ) * block
        bottom = self.selection.top() + math.ceil(
            (bounds.bottom() + 1 - self.selection.top()) / block
        ) * block
        crop = QRect(
            QPoint(max(self.selection.left(), left), max(self.selection.top(), top)),
            QPoint(
                min(self.selection.right(), right - 1),
                min(self.selection.bottom(), bottom - 1),
            ),
        )
        local = crop.translated(-self.selection.topLeft())
        pixel_left = round(local.left() * self._dpr)
        pixel_top = round(local.top() * self._dpr)
        pixel_right = round((local.left() + local.width()) * self._dpr)
        pixel_bottom = round((local.top() + local.height()) * self._dpr)
        cropped = source.copy(
            QRect(
                pixel_left,
                pixel_top,
                max(1, pixel_right - pixel_left),
                max(1, pixel_bottom - pixel_top),
            ).intersected(source.rect())
        )
        cropped.setDevicePixelRatio(self._dpr)
        return cropped, crop

    def _committed_annotation_layer(self):
        pixel_size = self._selection_pixel_size()
        if (
            not self._annotation_layer_dirty
            and not self._annotation_layer.isNull()
            and self._annotation_layer.size() == pixel_size
            and self._annotation_layer_selection == self.selection
        ):
            return self._annotation_layer
        layer = QPixmap(pixel_size)
        layer.setDevicePixelRatio(self._dpr)
        layer.fill(Qt.transparent)
        painter = QPainter(layer)
        self._prepare_annotation_layer_painter(painter)
        for annotation in self._annotations:
            if annotation["kind"] == "mosaic":
                painter.end()
                source = self._annotation_composite(layer)
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
        self._annotation_layer_selection = QRect(self.selection)
        self._annotation_layer_dirty = False
        return self._annotation_layer

    def _render_annotation_layer(self, annotations):
        """Rasterize a stable annotation set into one selection-sized layer."""
        layer = QPixmap(self._selection_pixel_size())
        layer.setDevicePixelRatio(self._dpr)
        layer.fill(Qt.transparent)
        painter = QPainter(layer)
        self._prepare_annotation_layer_painter(painter)
        for annotation in annotations:
            if annotation["kind"] == "mosaic":
                painter.end()
                source = self._annotation_composite(layer)
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
        return layer

    def _paint_annotation_on_layer(
        self,
        layer,
        annotation,
        *,
        mosaic_source=None,
        mosaic_source_rect=None,
    ):
        painter = QPainter(layer)
        self._prepare_annotation_layer_painter(painter)
        if annotation["kind"] == "mosaic":
            self._paint_annotation(
                painter,
                annotation,
                mosaic_source=mosaic_source,
                mosaic_source_rect=mosaic_source_rect,
            )
        else:
            self._paint_annotation(painter, annotation)
        painter.end()

    def _render_drag_foreground(self, suffix):
        """Render the stable suffix with canonical mosaic source ordering."""
        base = QPixmap(self._drag_base_layer)
        painter = QPainter(base)
        self._prepare_annotation_layer_painter(painter)
        for bounds, tile in self._drag_preview_tiles:
            painter.drawPixmap(bounds.topLeft(), tile)
        painter.end()
        foreground = QPixmap(self._selection_pixel_size())
        foreground.setDevicePixelRatio(self._dpr)
        foreground.fill(Qt.transparent)
        for annotation in suffix:
            source = None
            source_rect = None
            if annotation["kind"] == "mosaic":
                source, source_rect = self._mosaic_source_crop(
                    self._annotation_composite(base), annotation
                )
            self._paint_annotation_on_layer(
                foreground,
                annotation,
                mosaic_source=source,
                mosaic_source_rect=source_rect,
            )
            self._paint_annotation_on_layer(
                base,
                annotation,
                mosaic_source=source,
                mosaic_source_rect=source_rect,
            )
        return foreground

    def _render_drag_preview_layer(self, annotation):
        """Rasterize one vector element once, in its smallest safe bounds."""
        bounds = self._aligned_preview_bounds(annotation_bounds(annotation))
        if not bounds.isValid():
            return QPixmap(), QRect()
        pixel_size = QSize(
            round(bounds.width() * self._dpr),
            round(bounds.height() * self._dpr),
        )
        layer = QPixmap(pixel_size)
        layer.setDevicePixelRatio(self._dpr)
        layer.fill(Qt.transparent)
        painter = QPainter(layer)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(-bounds.topLeft())
        painter.setClipRect(bounds)
        self._paint_annotation(painter, annotation)
        painter.end()
        return layer, bounds

    def _aligned_preview_bounds(self, bounds):
        """Expand bounds so cached pixels share the committed layer's DPR phase."""
        if not bounds.isValid():
            return QRect()
        ratio = max(0.01, self._dpr)

        def aligned(value, origin):
            phase = (value - origin) * ratio
            return abs(phase - round(phase)) < 1e-6

        left = bounds.left()
        top = bounds.top()
        right = bounds.left() + bounds.width()
        bottom = bounds.top() + bounds.height()
        for _index in range(64):
            if aligned(left, self.selection.left()):
                break
            left -= 1
        for _index in range(64):
            if aligned(top, self.selection.top()):
                break
            top -= 1
        for _index in range(64):
            if aligned(right, self.selection.left()):
                break
            right += 1
        for _index in range(64):
            if aligned(bottom, self.selection.top()):
                break
            bottom += 1
        return QRect(left, top, max(1, right - left), max(1, bottom - top))

    def _begin_current_stroke_cache(self):
        """Prepare an incremental paint layer for a pen stroke in progress."""
        if self._current is None or self._current["kind"] != "pen":
            return
        self._current_stroke_tiles = {}
        self._current_stroke_point_count = 0
        self._current_stroke_dirty = self._extend_current_stroke_cache()

    def _has_current_stroke_cache(self):
        return (
            self._current is not None
            and self._current["kind"] == "pen"
            and self._current_stroke_tiles is not None
        )

    def _extend_current_stroke_cache(self):
        """Paint only the segments added since the previous mouse event."""
        if not self._has_current_stroke_cache():
            return QRect()
        points = self._current["points"]
        if len(points) <= self._current_stroke_point_count:
            return QRect()
        dirty = QRect()
        start = max(1, self._current_stroke_point_count)
        for index in range(start, len(points)):
            dirty = dirty.united(QRect(points[index - 1], points[index]).normalized())
        self._current_stroke_point_count = len(points)
        if not dirty.isValid():
            return QRect()
        padding = max(2, math.ceil(self._current["width"] / 2)) + 2
        dirty = dirty.adjusted(-padding, -padding, padding, padding)
        # Start the painted path a couple of points before the newly added
        # segments so neighbouring tiles share drawn pixels at their seam.
        path_start = max(0, start - 2)
        path = QPainterPath()
        path.moveTo(points[path_start])
        for index in range(path_start + 1, len(points)):
            path.lineTo(points[index])
        pen = QPen(
            self._current["color"],
            self._current["width"],
            Qt.SolidLine,
            Qt.RoundCap,
            Qt.RoundJoin,
        )
        for tile_bounds in self._tile_rects_covering(dirty):
            key = (tile_bounds.x(), tile_bounds.y())
            cached = self._current_stroke_tiles.get(key)
            if cached is None:
                tile = QPixmap(
                    round(tile_bounds.width() * self._dpr),
                    round(tile_bounds.height() * self._dpr),
                )
                tile.setDevicePixelRatio(self._dpr)
                tile.fill(Qt.transparent)
                cached = (tile_bounds, tile)
                self._current_stroke_tiles[key] = cached
            tile_bounds, tile = cached
            painter = QPainter(tile)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.translate(-tile_bounds.topLeft())
            painter.setPen(pen)
            painter.drawPath(path)
            painter.end()
        return dirty

    def _commit_current_stroke_cache(self):
        if not self._has_current_stroke_cache():
            return False
        layer = QPixmap(self._committed_annotation_layer())
        painter = QPainter(layer)
        for bounds, tile in self._current_stroke_tiles.values():
            painter.drawPixmap(bounds.topLeft() - self.selection.topLeft(), tile)
        painter.end()
        self._annotation_layer = layer
        self._annotation_layer_selection = QRect(self.selection)
        self._annotation_layer_dirty = False
        self._annotation_composite_cache = QPixmap()
        self._annotation_composite_key = None
        return True

    def _clear_current_stroke_cache(self):
        self._current_stroke_tiles = None
        self._current_stroke_point_count = 0
        self._current_stroke_dirty = QRect()

    def _pen_preview_key(self, annotation):
        color = QColor(annotation["color"])
        return (
            annotation.get("_geometry_revision", 0),
            color.rgba(),
            float(annotation["width"]),
            self.selection.x(),
            self.selection.y(),
            self.selection.width(),
            self.selection.height(),
            round(self._dpr * 1000),
        )

    def _remember_pen_preview(self, annotation, tiles, bounds, region):
        """Keep the most recent pen raster so editing never redraws its path."""
        if annotation["kind"] != "pen" or not tiles:
            return
        self._pen_preview_cache = {
            "annotation": annotation,
            "key": self._pen_preview_key(annotation),
            "tiles": [(QRect(tile_bounds), QPixmap(tile)) for tile_bounds, tile in tiles],
            "bounds": QRect(bounds),
            "region": QRegion(region),
        }

    def _cached_pen_preview(self, annotation):
        cached = self._pen_preview_cache
        if (
            cached is None
            or cached["annotation"] is not annotation
            or cached["key"] != self._pen_preview_key(annotation)
            or not cached["bounds"].contains(annotation_bounds(annotation))
        ):
            return None
        return cached

    def _pen_preview_for_annotation(self, annotation):
        cached = self._pen_preview_cache
        if cached is not None and cached["annotation"] is annotation:
            return cached
        return None

    def _discard_pen_preview_cache(self, annotation=None):
        cached = self._pen_preview_cache
        if cached is None:
            return
        if annotation is None or cached["annotation"] is annotation:
            self._pen_preview_cache = None

    def _remember_current_pen_preview(self, annotation):
        if not self._current_stroke_tiles:
            return
        bounds = annotation_bounds(annotation)
        if not self.selection.contains(bounds):
            return
        tiles = list(self._current_stroke_tiles.values())
        self._remember_pen_preview(
            annotation,
            tiles,
            bounds,
            self._annotation_renderer().preview_region(annotation),
        )

    def _commit_resized_pen_preview(self, annotation):
        """Rebuild a resized pen cache with fixed stroke width, then commit it."""
        layer, bounds = self._render_drag_preview_layer(annotation)
        if layer.isNull() or not bounds.isValid() or self._drag_base_layer.isNull():
            return False
        ordered_rects = self._preview_tile_rects(annotation, bounds)
        self._drag_preview_tiles = self._split_preview_tiles(
            layer, bounds, ordered_rects
        )
        self._drag_preview_bounds = QRect(bounds)
        self._drag_preview_region = self._annotation_renderer().preview_region(
            annotation
        ).intersected(QRegion(bounds))
        self._drag_preview_offset = QPoint()
        if not self._commit_drag_preview_layer():
            return False
        self._remember_pen_preview(
            annotation,
            self._drag_preview_tiles,
            self._drag_preview_bounds,
            self._drag_preview_region,
        )
        return True

    def _tile_rects_covering(self, bounds, *, clip_to_selection=True):
        bounds = (
            bounds.intersected(self.selection)
            if clip_to_selection
            else QRect(bounds)
        )
        if not bounds.isValid():
            return []
        size = self.RASTER_TILE_SIZE
        left = (bounds.left() - self.selection.left()) // size
        right = (bounds.right() - self.selection.left()) // size
        top = (bounds.top() - self.selection.top()) // size
        bottom = (bounds.bottom() - self.selection.top()) // size
        tiles = []
        for row in range(top, bottom + 1):
            for column in range(left, right + 1):
                tile = QRect(
                    self.selection.left() + column * size,
                    self.selection.top() + row * size,
                    size,
                    size,
                )
                if clip_to_selection:
                    tile = tile.intersected(self.selection)
                if tile.isValid():
                    tiles.append(tile)
        return tiles

    def _preview_tile_rects(self, annotation, bounds):
        """Choose bounded raster tiles without scanning a large alpha mask."""
        preview_region = self._annotation_renderer().preview_region(annotation)
        preview_region = preview_region.intersected(QRegion(bounds))
        tiles = {}
        for region_bounds in preview_region:
            for tile in self._tile_rects_covering(
                region_bounds, clip_to_selection=False
            ):
                clipped = tile.intersected(bounds)
                if clipped.isValid():
                    tiles[(tile.x(), tile.y())] = clipped
        if not tiles:
            for tile in self._tile_rects_covering(
                bounds, clip_to_selection=False
            ):
                clipped = tile.intersected(bounds)
                if clipped.isValid():
                    tiles[(tile.x(), tile.y())] = clipped
        return [tiles[key] for key in sorted(tiles)]

    def _raster_tile_rects(self, layer, bounds):
        alpha = QRegion(QBitmap.fromImage(layer.toImage().createAlphaMask()))
        tiles = {}
        ratio = max(0.01, self._dpr)
        for pixel_rect in alpha:
            logical = QRect(
                bounds.left() + math.floor(pixel_rect.left() / ratio),
                bounds.top() + math.floor(pixel_rect.top() / ratio),
                max(1, math.ceil(pixel_rect.width() / ratio)),
                max(1, math.ceil(pixel_rect.height() / ratio)),
            )
            for tile in self._tile_rects_covering(logical):
                tiles[(tile.x(), tile.y())] = tile.intersected(bounds)
        return [tiles[key] for key in sorted(tiles)]

    def _split_preview_tiles(self, layer, bounds, tile_rects):
        tiles = []
        for tile_bounds in tile_rects:
            local = tile_bounds.translated(-bounds.topLeft())
            left = round(local.left() * self._dpr)
            top = round(local.top() * self._dpr)
            right = round((local.left() + local.width()) * self._dpr)
            bottom = round((local.top() + local.height()) * self._dpr)
            pixel_rect = QRect(
                left,
                top,
                max(1, right - left),
                max(1, bottom - top),
            ).intersected(layer.rect())
            tile = layer.copy(pixel_rect)
            tile.setDevicePixelRatio(self._dpr)
            tiles.append((tile_bounds, tile))
        return tiles

    def _erase_annotations(self, eraser):
        """Commit an eraser stroke by replacing touched items with fragments."""
        self._record_undo({"type": "erase", "before": list(self._annotations)})
        erased_bounds = annotation_bounds(eraser)
        annotations = []
        for annotation in self._annotations:
            if (
                annotation["kind"] == "eraser"
                or not annotation_bounds(annotation).intersects(erased_bounds)
            ):
                annotations.append(annotation)
                continue
            annotations.extend(self._erase_annotation(annotation, eraser))
        self._annotations = annotations
        self._active_annotation = None
        cached = self._pen_preview_cache
        if cached is not None and not any(
            item is cached["annotation"] for item in self._annotations
        ):
            self._discard_pen_preview_cache()
        self._renderer.retain_annotations(self._annotations)
        self._invalidate_annotation_layer()

    def _erase_annotation(self, annotation, eraser):
        """Return the visible connected pieces of one erased annotation."""
        image, bounds = self._rasterize_annotation(annotation)
        if image.isNull():
            return []
        original_alpha = image.createAlphaMask()
        original_components = self._image_components(image)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(-bounds.topLeft())
        self._paint_annotation(painter, eraser)
        painter.end()
        if image.createAlphaMask() == original_alpha:
            return [annotation]
        components = self._image_components(image)
        if not components:
            return []
        # Text and pre-existing multi-island artwork should stay one editable
        # item. A connected vector item, however, gets one anchor per newly
        # disconnected visible piece.
        if len(original_components) != 1:
            components = [self._components_region(components)]
        return [
            self._fragment_from_component(image, bounds, component, annotation)
            for component in components
        ]

    def _rasterize_annotation(self, annotation):
        bounds = annotation_bounds(annotation).intersected(self.selection)
        if not bounds.isValid():
            return QImage(), QRect()
        image = QImage(
            round(bounds.width() * self._dpr),
            round(bounds.height() * self._dpr),
            QImage.Format_ARGB32_Premultiplied,
        )
        image.setDevicePixelRatio(self._dpr)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(-bounds.topLeft())
        if annotation["kind"] == "mosaic":
            source = self._desktop
            source_rect = QRect(
                0,
                0,
                round(self._desktop.width() / self._dpr),
                round(self._desktop.height() / self._dpr),
            )
            if annotation in self._annotations:
                index = self._annotations.index(annotation)
                prefix = self._render_annotation_layer(self._annotations[:index])
                source = self._annotation_composite(prefix)
                source_rect = QRect(self.selection)
            self._paint_annotation(
                painter,
                annotation,
                mosaic_source=source,
                mosaic_source_rect=source_rect,
            )
        else:
            self._paint_annotation(painter, annotation)
        painter.end()
        return image, bounds

    @staticmethod
    def _image_components(image):
        region = QRegion(QBitmap.fromImage(image.createAlphaMask()))
        rects = [QRect(rect) for rect in region]
        if not rects:
            return []
        parents = list(range(len(rects)))

        def root(index):
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def join(first, second):
            first = root(first)
            second = root(second)
            if first != second:
                parents[second] = first

        active = []
        for index, rect in sorted(
            enumerate(rects), key=lambda item: item[1].top()
        ):
            active = [
                other for other in active if rects[other].bottom() + 1 >= rect.top()
            ]
            expanded = rect.adjusted(-1, -1, 1, 1)
            for other in active:
                if expanded.intersects(rects[other]):
                    join(index, other)
            active.append(index)
        groups = {}
        for index, rect in enumerate(rects):
            group = root(index)
            groups[group] = groups.get(group, QRegion()).united(QRegion(rect))
        return list(groups.values())

    @staticmethod
    def _components_region(components):
        region = QRegion()
        for component in components:
            region = region.united(component)
        return region

    def _fragment_from_component(self, image, bounds, component, source):
        ratio = max(0.01, self._dpr)
        component_bounds = component.boundingRect()
        left = math.floor(component_bounds.left() / ratio)
        top = math.floor(component_bounds.top() / ratio)
        right = math.ceil((component_bounds.right() + 1) / ratio)
        bottom = math.ceil((component_bounds.bottom() + 1) / ratio)
        pixel_rect = QRect(
            round(left * ratio),
            round(top * ratio),
            max(1, round((right - left) * ratio)),
            max(1, round((bottom - top) * ratio)),
        ).intersected(image.rect())
        source_fragment = image.copy(pixel_rect)
        source_fragment.setDevicePixelRatio(1.0)
        fragment = QImage(source_fragment.size(), source_fragment.format())
        fragment.fill(Qt.transparent)
        painter = QPainter(fragment)
        painter.setClipRegion(
            component.intersected(QRegion(pixel_rect)).translated(
                -pixel_rect.topLeft()
            )
        )
        painter.drawImage(QPoint(), source_fragment)
        painter.end()
        fragment.setDevicePixelRatio(self._dpr)
        start = bounds.topLeft() + QPoint(left, top)
        end = start + QPoint(right - left - 1, bottom - top - 1)
        return {
            "kind": "fragment",
            "start": start,
            "end": end,
            "color": QColor(source["color"]),
            "width": source["width"],
            "image": fragment,
        }

    def _annotation_composite(self, annotation_layer):
        """Combine the frozen desktop and annotations for mosaic sampling."""
        cache_key = (
            annotation_layer.cacheKey(),
            self._desktop.cacheKey(),
            self.selection.x(),
            self.selection.y(),
            self.selection.width(),
            self.selection.height(),
            round(self._dpr * 1000),
        )
        if (
            not self._annotation_composite_cache.isNull()
            and self._annotation_composite_key == cache_key
        ):
            return self._annotation_composite_cache
        composite = QPixmap(self._selection_pixel_size())
        composite.setDevicePixelRatio(self._dpr)
        composite.fill(Qt.transparent)
        painter = QPainter(composite)
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
        painter.drawPixmap(QPoint(), annotation_layer)
        painter.end()
        self._annotation_composite_cache = composite
        self._annotation_composite_key = cache_key
        return self._annotation_composite_cache

    def _invalidate_annotation_layer(self):
        self._annotation_layer_dirty = True
        self._annotation_composite_cache = QPixmap()
        self._annotation_composite_key = None

    def _refresh_annotation_layer_region(self, dirty):
        """Recompose only pixels affected by an interactive element edit."""
        dirty = dirty.intersected(self.selection)
        if not dirty.isValid():
            return
        if (
            self._annotation_layer_dirty
            or self._annotation_layer.isNull()
            or self._annotation_layer.size() != self._selection_pixel_size()
            or self._annotation_layer_selection != self.selection
        ):
            self._invalidate_annotation_layer()
            return

        painter = QPainter(self._annotation_layer)
        self._prepare_annotation_layer_painter(painter)
        painter.setClipRect(dirty, Qt.IntersectClip)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(dirty, Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        for annotation in self._annotations:
            if not annotation_bounds(annotation).intersects(dirty):
                continue
            if annotation["kind"] == "mosaic":
                painter.end()
                source = self._annotation_composite(self._annotation_layer)
                painter = QPainter(self._annotation_layer)
                self._prepare_annotation_layer_painter(painter)
                painter.setClipRect(dirty, Qt.IntersectClip)
                self._paint_annotation(
                    painter,
                    annotation,
                    mosaic_source=source,
                    mosaic_source_rect=self.selection,
                )
            else:
                self._paint_annotation(painter, annotation)
        painter.end()
        self._annotation_composite_cache = QPixmap()
        self._annotation_composite_key = None

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

    def _paint_annotation_handles(self, painter):
        bounds = self._editable_annotation_bounds()
        if not bounds.isValid():
            return
        painter.save()
        painter.setPen(QPen(QColor("#55b6ff"), 1, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(bounds)
        painter.setPen(QPen(Qt.white, 1))
        painter.setBrush(QColor("#55b6ff"))
        for point in handle_points(bounds).values():
            painter.drawRect(QRect(point.x() - 4, point.y() - 4, 8, 8))
        painter.restore()

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
        if not (self.selection.isValid() and self.selection.width() > 1):
            window_rect = self._window_at(point)
            if window_rect.isValid():
                self._drag_mode = "window_pending"
                self._pending_window = QRect(window_rect)
            else:
                self._drag_mode = "select"
                self.selection = QRect(point, point)
            return
        locked = self._selection_is_locked()
        if self._active_annotation in self._annotations and not self._tool:
            handle = hit_handle(self._editable_annotation_bounds(), point)
            if handle:
                self._drag_mode = "resize_element"
                self._handle = handle
                self._begin_element_resize(self._active_annotation)
                return
        handle = hit_handle(self.selection, point) if not locked else ""
        if handle:
            self._drag_mode = "resize"
            self._handle = handle
            self._selection_start = QRect(self.selection)
            return
        if self._tool and self._tool != "text" and self.selection.contains(point):
            self._drag_mode = "draw_pending"
            return
        if not self.selection.contains(point):
            self._start_new_selection(point)
            return
        annotation = self._annotation_at(point)
        if annotation is not None:
            self._select_annotation(annotation)
            if annotation["kind"] == "text":
                self._drag_mode = "move_text"
                self._moving_text = annotation
                self._moving_text_start = QPoint(annotation["start"])
            else:
                self._drag_mode = "move_element"
                self._begin_element_move(annotation)
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
        self._drag_mode = "move"
        self._selection_start = QRect(self.selection)

    def _start_new_selection(self, point):
        """Discard the old annotated capture before starting a new region."""
        old_selection_dirty = self.rect()
        editor = self._text_editor
        if editor is not None:
            self._text_editor = None
            self._editing_text_index = -1
            editor.removeEventFilter(self)
            editor.hide()
            editor.deleteLater()
        self._annotations.clear()
        self._undo_stack.clear()
        self._active_annotation = None
        self._current = None
        self._element_start = None
        self._element_bounds_start = QRect()
        self._selection_start = QRect()
        self._handle = ""
        self._moving_text = None
        self._pending_window = QRect()
        self._hovered_window = QRect()
        self._clear_current_stroke_cache()
        self._discard_pen_preview_cache()
        self._clear_drag_preview()
        self._renderer.retain_annotations(self._annotations)
        self._annotation_layer = QPixmap()
        self._annotation_layer_selection = QRect()
        self._invalidate_annotation_layer()
        self.selection = QRect(point, point)
        self._cursor_pos = QPoint(point)
        self._drag_mode = "select"
        self.toolbar.hide()
        self.selection_options.hide()
        # Flush the old frame synchronously. On macOS, queued partial updates
        # can leave stale backing-store tiles while replacement drag starts.
        self.repaint(old_selection_dirty)

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        preselection_damage = QRegion()
        if not (self.selection.isValid() and self.selection.width() > 1):
            preselection_damage = QRegion(
                self._magnifier_rect(self._cursor_pos).adjusted(-3, -3, 3, 3)
            )
            if self._hovered_window.isValid():
                preselection_damage = preselection_damage.united(
                    QRegion(self._hovered_window.adjusted(-3, -3, 3, 3))
                )
        self._cursor_pos = point
        old_annotation_region = self._active_draw_region()
        old_preview_region = self._active_preview_region()
        old_suffix_region = self._drag_dependent_suffix_region()
        old_selection_region = self._selection_dirty_region(self.selection)
        if not self.selection.isValid() and not self._drag_mode:
            self._hovered_window = self._window_at(point)
        if self._drag_mode == "window_pending":
            if (point - self._drag_start).manhattanLength() > 4:
                self._drag_mode = "select"
                self._pending_window = QRect()
                self._hovered_window = QRect()
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
                if self._current["kind"] in ("pen", "mosaic", "eraser"):
                    append_brush_points(self._current, point)
                self._begin_current_stroke_cache()
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
        elif self._drag_mode == "move_element" and self._active_annotation is not None:
            self._move_active_annotation(point)
        elif self._drag_mode == "resize_element" and self._active_annotation is not None:
            target = resize_selection(
                self._element_bounds_start,
                self._handle,
                point,
                self.selection,
            )
            if self._has_drag_preview():
                self._resize_preview_bounds = target
            else:
                self._restore_active_annotation()
                resize_annotation(
                    self._active_annotation,
                    self._element_bounds_start,
                    target,
                )
        elif self._drag_mode == "annotate" and self._current:
            self._current["end"] = point
            if self._current["kind"] in ("pen", "mosaic", "eraser"):
                append_brush_points(self._current, point)
            self._current_stroke_dirty = self._extend_current_stroke_cache()
        elif not self._drag_mode:
            self._refresh_hover_cursor(point)
        if self._drag_mode in ("move", "resize", "select", "window_pending"):
            self._sync_selection_options()
            new_selection_region = self._selection_dirty_region(self.selection)
            dirty = (
                QRegion(old_selection_region)
                .united(QRegion(new_selection_region))
                .united(preselection_damage)
            )
            self.update(dirty)
        elif self._drag_mode in (
            "annotate", "move_text", "move_element", "resize_element"
        ):
            if self._has_current_stroke_cache() and self._current_stroke_dirty.isValid():
                self.update(self._current_stroke_dirty.intersected(self.rect()))
                return
            new_annotation_region = self._active_draw_region()
            dirty = old_annotation_region.united(new_annotation_region)
            if self._drag_mode == "move_text" or (
                self._drag_mode in ("move_element", "resize_element")
                and not self._has_drag_preview()
            ):
                self._refresh_annotation_layer_region(dirty)
            if self._has_drag_preview():
                preview_dirty = (
                    old_preview_region
                    .united(self._active_preview_region())
                    .united(old_suffix_region)
                    .united(self._drag_dependent_suffix_region())
                )
                if not preview_dirty.isEmpty():
                    self.update(preview_dirty)
            elif dirty.isValid():
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
        if (
            self._drag_mode in ("move_element", "resize_element")
            and self._active_annotation is not None
        ):
            bounds = annotation_bounds(self._active_annotation)
            if self._has_drag_preview():
                if self._drag_mode == "resize_element":
                    bounds = QRect(self._resize_preview_bounds)
                else:
                    bounds.translate(self._drag_preview_offset)
            handles = self._editable_annotation_bounds().adjusted(-5, -5, 5, 5)
            return bounds.united(handles)
        return QRect()

    def _active_preview_region(self):
        if not self._has_drag_preview():
            return QRegion()
        if self._drag_mode == "resize_element":
            bounds = self._resize_preview_bounds
            if not bounds.isValid():
                return QRegion()
            transform = self._resize_preview_transform()
            region = QRegion()
            if transform is not None:
                for preview_bounds in self._drag_preview_region:
                    region = region.united(
                        QRegion(
                            transform.mapRect(QRectF(preview_bounds))
                            .toAlignedRect()
                            .adjusted(-2, -2, 2, 2)
                        )
                    )
            region = region.united(self._outline_region(bounds))
            for point in handle_points(bounds).values():
                region = region.united(
                    QRegion(QRect(point.x() - 5, point.y() - 5, 11, 11))
                )
            return region.intersected(QRegion(self.rect()))
        offset = self._drag_preview_offset
        region = self._drag_preview_region.translated(offset)
        bounds = self._element_bounds_start.translated(offset)
        if bounds.isValid():
            region = region.united(self._outline_region(bounds))
            for point in handle_points(bounds).values():
                region = region.united(
                    QRegion(QRect(point.x() - 5, point.y() - 5, 11, 11))
                )
        return region.intersected(QRegion(self.rect()))

    def _resize_preview_transform(self):
        source = self._element_bounds_start
        target = self._resize_preview_bounds
        if not source.isValid() or not target.isValid():
            return None
        scale_x = target.width() / max(1, source.width())
        scale_y = target.height() / max(1, source.height())
        return QTransform(
            scale_x,
            0.0,
            0.0,
            scale_y,
            target.left() - source.left() * scale_x,
            target.top() - source.top() * scale_y,
        )

    @staticmethod
    def _outline_region(bounds):
        if not bounds.isValid():
            return QRegion()
        padding = 3
        outer = QRegion(bounds.adjusted(-padding, -padding, padding, padding))
        inner = bounds.adjusted(padding, padding, -padding, -padding)
        return outer.subtracted(QRegion(inner)) if inner.isValid() else outer

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
                annotation = new_annotation(
                    self._tool,
                    self._drag_start,
                    self._drag_start,
                    self._color,
                    self._width,
                )
                self._annotations.append(annotation)
                self._record_undo(
                    {
                        "type": "add",
                        "annotation": annotation,
                        "index": len(self._annotations) - 1,
                    }
                )
                self._renderer.retain_annotations(self._annotations)
                self._invalidate_annotation_layer()
        if self._drag_mode == "annotate" and self._current:
            if self._current["kind"] == "eraser":
                self._erase_annotations(self._current)
            else:
                cached_stroke = self._commit_current_stroke_cache()
                if cached_stroke:
                    self._remember_current_pen_preview(self._current)
                self._annotations.append(self._current)
                self._record_undo(
                    {
                        "type": "add",
                        "annotation": self._current,
                        "index": len(self._annotations) - 1,
                    }
                )
                self._renderer.retain_annotations(self._annotations)
                if not cached_stroke:
                    self._invalidate_annotation_layer()
            self._clear_current_stroke_cache()
            self._current = None
        if self._drag_mode == "move":
            delta = self.selection.topLeft() - self._selection_start.topLeft()
            if not delta.isNull() and self._annotations:
                self._record_undo(
                    {
                        "type": "move",
                        "annotations": list(self._annotations),
                        "delta": delta,
                        "selection_before": QRect(self._selection_start),
                        "selection_after": QRect(self.selection),
                    }
                )
                translate_annotations(self._annotations, delta)
        force_repaint = False
        if self._drag_mode == "move_element" and self._has_drag_preview():
            annotation = self._active_annotation
            offset = QPoint(self._drag_preview_offset)
            translate_annotations([annotation], offset)
            if not self._translation_preserves_dpr_phase(offset):
                self._rebuild_drag_preview_tiles(annotation)
                offset = QPoint()
            if not self._commit_drag_preview_layer():
                self._invalidate_annotation_layer()
            self._remember_pen_preview(
                annotation,
                [
                    (bounds.translated(offset), tile)
                    for bounds, tile in self._drag_preview_tiles
                ],
                self._drag_preview_bounds.translated(offset),
                self._drag_preview_region.translated(offset),
            )
            self._clear_drag_preview()
            force_repaint = True
        if self._drag_mode == "resize_element" and self._has_drag_preview():
            annotation = self._active_annotation
            source_bounds = QRect(self._element_bounds_start)
            target_bounds = QRect(self._resize_preview_bounds)
            resize_annotation(
                annotation,
                source_bounds,
                target_bounds,
            )
            if annotation["kind"] != "pen" or not self._commit_resized_pen_preview(
                annotation
            ):
                self._discard_pen_preview_cache(annotation)
                self._invalidate_annotation_layer()
            self._clear_drag_preview()
            force_repaint = True
        if self._drag_mode == "move_element" and self._active_annotation is not None:
            before = self._gesture_geometry_before
            if before.isValid():
                after = annotation_geometry(self._active_annotation)
                delta = after.topLeft() - before.topLeft()
                if not delta.isNull():
                    self._record_undo(
                        {
                            "type": "move",
                            "annotations": [self._active_annotation],
                            "delta": delta,
                        }
                    )
        elif (
            self._drag_mode == "resize_element"
            and self._active_annotation is not None
        ):
            before = self._gesture_geometry_before
            if before.isValid():
                after = annotation_geometry(self._active_annotation)
                if before != after:
                    self._record_undo(
                        {
                            "type": "resize",
                            "annotation": self._active_annotation,
                            "source": before,
                            "target": after,
                        }
                    )
        elif self._drag_mode == "move_text" and self._moving_text is not None:
            delta = self._moving_text["start"] - self._moving_text_start
            if not delta.isNull():
                self._record_undo(
                    {
                        "type": "move",
                        "annotations": [self._moving_text],
                        "delta": delta,
                    }
                )
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
        if force_repaint:
            # A completed cached gesture replaces pixels rather than merely
            # adding them, so force the native backing store to be reconciled.
            self.repaint()
        else:
            self.update()

    def mouseDoubleClickEvent(self, event):
        point = event.position().toPoint()
        annotation = self._annotation_at(point)
        if annotation is not None:
            self._select_annotation(annotation)
            if annotation["kind"] == "text":
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
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete_active_annotation()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        annotation = self._annotation_at(event.pos())
        if annotation is None:
            event.ignore()
            return
        self._select_annotation(annotation)
        menu = QMenu(self)
        menu.setObjectName("screenshotContextMenu")
        apply_style(menu, "tools.screenshot.overlay:workspace")
        delete_action = menu.addAction("删除")
        delete_action.triggered.connect(self._delete_active_annotation)
        menu.exec(event.globalPos())

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
            self._active_annotation = None
        else:
            self._tool = ""
        self._refresh_cursor()
        self.update()

    def _choose_color(self, color):
        self._color = QColor(color)
        if self._active_annotation is not None:
            current = QColor(self._active_annotation["color"])
            if current != self._color:
                self._active_annotation["color"] = QColor(self._color)
                self._invalidate_annotation_layer()
                self.update()
            if self._text_editor is not None:
                self._text_editor.setProperty("annotationColor", self._color)
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
            current = float(self._active_annotation["width"])
            if current != self._width:
                self._active_annotation["width"] = self._width
                self._invalidate_annotation_layer()
                self.update()
            if self._text_editor is not None:
                self._text_editor.setProperty("annotationWidth", self._width)
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
        if self._tool not in ("mosaic", "eraser"):
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
        painter.drawRect(QRectF(3, 3, diameter, diameter))
        painter.setPen(QPen(Qt.white, 1))
        painter.drawRect(QRectF(3, 3, diameter, diameter))
        painter.end()
        self.setCursor(QCursor(pixmap, size // 2, size // 2))

    def _hide_popups(self):
        self.toolbar.hide_popups()

    def _begin_text_edit(self, point, *, annotation=None):
        self._commit_text()
        text = ""
        if annotation is not None:
            self._editing_text_index = self._annotations.index(annotation)
            self._record_undo(
                {
                    "type": "text_edit",
                    "annotation": annotation,
                    "snapshot": copy.deepcopy(annotation),
                    "index": self._editing_text_index,
                }
            )
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
            if annotation["kind"] != "eraser" and annotation_contains(annotation, point):
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

    def _begin_element_move(self, annotation):
        self._element_bounds_start = self._editable_annotation_bounds()
        self._gesture_geometry_before = annotation_geometry(annotation)
        if annotation["kind"] not in (
            "arrow", "ellipse", "fragment", "pen", "rect"
        ):
            self._element_start = copy.deepcopy(annotation)
            return
        self._element_start = annotation
        self._begin_element_preview(annotation)

    def _begin_element_resize(self, annotation):
        self._element_bounds_start = self._editable_annotation_bounds()
        self._gesture_geometry_before = annotation_geometry(annotation)
        self._resize_preview_bounds = QRect(self._element_bounds_start)
        if annotation["kind"] not in (
            "arrow", "ellipse", "fragment", "pen", "rect"
        ):
            self._element_start = copy.deepcopy(annotation)
            return
        self._element_start = annotation
        self._begin_element_preview(annotation)

    def _begin_element_preview(self, annotation):
        """Rasterize an editable vector once for move/resize interaction."""
        self._drag_preview_annotation = annotation
        self._drag_preview_offset = QPoint()
        cached = self._cached_pen_preview(annotation)
        if cached is not None:
            self._drag_preview_layer = QPixmap()
            self._drag_preview_bounds = QRect(cached["bounds"])
            self._drag_preview_tiles = list(cached["tiles"])
            self._drag_preview_region = QRegion(cached["region"])
        else:
            self._rebuild_drag_preview_tiles(annotation)
            self._remember_pen_preview(
                annotation,
                self._drag_preview_tiles,
                self._drag_preview_bounds,
                self._drag_preview_region,
            )
            self._drag_preview_layer = QPixmap()
        index = next(
            index
            for index, item in enumerate(self._annotations)
            if item is annotation
        )
        self._drag_base_layer = self._render_annotation_layer(
            self._annotations[:index]
        )
        self._drag_scene_layer = self._annotation_composite(self._drag_base_layer)
        suffix = self._annotations[index + 1 :]
        has_suffix_mosaic = any(item["kind"] == "mosaic" for item in suffix)
        if has_suffix_mosaic:
            self._drag_foreground_layer = self._render_drag_foreground(suffix)
            self._drag_suffix_annotations = suffix
        else:
            self._drag_foreground_layer = (
                self._render_annotation_layer(suffix) if suffix else QPixmap()
            )
            self._drag_suffix_annotations = []

    def _rebuild_drag_preview_tiles(self, annotation):
        layer, bounds = self._render_drag_preview_layer(annotation)
        self._drag_preview_bounds = QRect(bounds)
        tile_rects = self._preview_tile_rects(annotation, bounds)
        self._drag_preview_tiles = self._split_preview_tiles(
            layer,
            bounds,
            tile_rects,
        )
        self._drag_preview_region = self._annotation_renderer().preview_region(
            annotation
        ).intersected(QRegion(bounds))
        self._drag_preview_offset = QPoint()
        self._drag_preview_layer = QPixmap()
        return bool(self._drag_preview_tiles)

    def _translation_preserves_dpr_phase(self, offset):
        ratio = max(0.01, self._dpr)
        return all(
            abs(value * ratio - round(value * ratio)) < 1e-6
            for value in (offset.x(), offset.y())
        )

    def _has_drag_preview(self):
        return (
            self._drag_preview_annotation is not None
            and self._drag_preview_annotation is self._active_annotation
        )

    def _clear_drag_preview(self):
        self._drag_preview_annotation = None
        self._drag_preview_offset = QPoint()
        self._drag_preview_region = None
        self._drag_preview_bounds = QRect()
        self._resize_preview_bounds = QRect()
        self._drag_preview_layer = QPixmap()
        self._drag_preview_tiles = []
        self._drag_base_layer = QPixmap()
        self._drag_scene_layer = QPixmap()
        self._drag_foreground_layer = QPixmap()
        self._drag_suffix_annotations = []
        self._drag_dynamic_scene_layer = QPixmap()
        self._drag_dynamic_scene_key = None

    def _commit_drag_preview_layer(self):
        """Commit cached pixels in canonical annotation z-order on release."""
        active = self._drag_preview_annotation
        if active not in self._annotations or not self._drag_preview_tiles:
            return False
        layer = QPixmap(self._selection_pixel_size())
        layer.setDevicePixelRatio(self._dpr)
        layer.fill(Qt.transparent)
        painter = QPainter(layer)
        self._prepare_annotation_layer_painter(painter)
        for annotation in self._annotations:
            if annotation is active:
                for bounds, tile in self._drag_preview_tiles:
                    painter.drawPixmap(
                        bounds.topLeft() + self._drag_preview_offset,
                        tile,
                    )
                continue
            if annotation["kind"] == "mosaic":
                painter.end()
                source = self._annotation_composite(layer)
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
        self._annotation_layer_selection = QRect(self.selection)
        self._annotation_layer_dirty = False
        self._annotation_composite_cache = QPixmap()
        self._annotation_composite_key = None
        return True

    def _editable_annotation_bounds(self):
        annotation = self._active_annotation
        if annotation is None:
            return QRect()
        bounds = annotation_geometry(annotation)
        if not bounds.isValid():
            return QRect()
        if bounds.width() < 16:
            bounds.adjust(-8, 0, 8, 0)
        if bounds.height() < 16:
            bounds.adjust(0, -8, 0, 8)
        if self._has_drag_preview():
            if self._drag_mode == "resize_element":
                bounds = QRect(self._resize_preview_bounds)
            else:
                bounds.translate(self._drag_preview_offset)
        return bounds

    def _restore_active_annotation(self):
        if self._active_annotation is None or self._element_start is None:
            return
        self._active_annotation.clear()
        self._active_annotation.update(copy.deepcopy(self._element_start))

    def _move_active_annotation(self, point):
        if self._active_annotation is None or self._element_start is None:
            return
        desired = point - self._drag_start
        source = self._element_bounds_start
        moved = source.translated(desired)
        if moved.left() < self.selection.left():
            desired.setX(desired.x() + self.selection.left() - moved.left())
        if moved.right() > self.selection.right():
            desired.setX(desired.x() + self.selection.right() - moved.right())
        if moved.top() < self.selection.top():
            desired.setY(desired.y() + self.selection.top() - moved.top())
        if moved.bottom() > self.selection.bottom():
            desired.setY(desired.y() + self.selection.bottom() - moved.bottom())
        if self._has_drag_preview():
            self._drag_preview_offset = desired
            return
        self._restore_active_annotation()
        translate_annotations([self._active_annotation], desired)

    def _delete_active_annotation(self):
        annotation = self._active_annotation
        if annotation not in self._annotations:
            return
        index = self._annotations.index(annotation)
        self._record_undo(
            {"type": "remove", "annotation": annotation, "index": index}
        )
        self._annotations.remove(annotation)
        self._discard_pen_preview_cache(annotation)
        self._active_annotation = None
        self._renderer.retain_annotations(self._annotations)
        self._invalidate_annotation_layer()
        self.update()

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

    def _index_of_annotation(self, annotation):
        for index, item in enumerate(self._annotations):
            if item is annotation:
                return index
        return -1

    def _record_undo(self, record):
        """Remember an operation so _undo can reverse it (LIFO)."""
        self._undo_stack.append(record)
        if len(self._undo_stack) > 500:
            del self._undo_stack[: len(self._undo_stack) - 500]

    def _undo(self):
        if self._undo_stack:
            record = self._undo_stack.pop()
            self._apply_undo(record)
            return
        # Legacy fallback: with no recorded operation, drop the last annotation.
        if self._annotations:
            removed = self._annotations.pop()
            self._discard_pen_preview_cache(removed)
            if self._active_annotation is removed:
                self._active_annotation = None
            self._renderer.retain_annotations(self._annotations)
            self._invalidate_annotation_layer()
            self.update()

    def _apply_undo(self, record):
        kind = record["type"]
        if kind == "add":
            annotation = record["annotation"]
            index = self._index_of_annotation(annotation)
            if index >= 0:
                del self._annotations[index]
            if self._active_annotation is annotation:
                self._active_annotation = None
            self._discard_pen_preview_cache(annotation)
        elif kind == "remove":
            annotation = record["annotation"]
            if self._index_of_annotation(annotation) < 0:
                index = min(record["index"], len(self._annotations))
                self._annotations.insert(index, annotation)
            self._active_annotation = None
            self._discard_pen_preview_cache(annotation)
        elif kind == "move":
            delta = record["delta"]
            if not delta.isNull():
                translate_annotations(record["annotations"], -delta)
            for annotation in record["annotations"]:
                self._discard_pen_preview_cache(annotation)
            if "selection_before" in record:
                self.selection = QRect(record["selection_before"])
                self._position_toolbar()
                self._sync_selection_options()
        elif kind == "resize":
            annotation = record["annotation"]
            resize_annotation(annotation, record["target"], record["source"])
            self._discard_pen_preview_cache(annotation)
        elif kind == "erase":
            self._annotations = list(record["before"])
            self._active_annotation = None
            self._discard_pen_preview_cache()
        elif kind == "text_edit":
            annotation = record["annotation"]
            annotation.clear()
            annotation.update(copy.deepcopy(record["snapshot"]))
            if self._index_of_annotation(annotation) < 0:
                index = min(record["index"], len(self._annotations))
                self._annotations.insert(index, annotation)
            self._active_annotation = None
            self._discard_pen_preview_cache(annotation)
        self._clear_drag_preview()
        self._renderer.retain_annotations(self._annotations)
        self._invalidate_annotation_layer()
        self.update()

    def _refresh_hover_cursor(self, point):
        locked = self._selection_is_locked()
        annotation_handle = (
            hit_handle(self._editable_annotation_bounds(), point)
            if self._active_annotation in self._annotations and not self._tool
            else ""
        )
        handle = annotation_handle or (
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
