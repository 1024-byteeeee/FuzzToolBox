"""Rendering engine for screenshot annotations."""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QPolygon,
    QRegion,
)

from .annotations import annotation_bounds, arrow_head_length


class AnnotationRenderer:
    """Render annotations against one immutable frozen desktop image."""

    MOSAIC_BLOCK_SIZE = 12
    PEN_CHUNK_SEGMENTS = 64

    def __init__(
        self,
        desktop: QPixmap,
        selection: QRect,
        device_pixel_ratio: float,
        fallback_font_family: str,
    ) -> None:
        self._desktop = desktop
        self._selection = QRect(selection)
        self._device_pixel_ratio = device_pixel_ratio
        self._fallback_font_family = fallback_font_family
        self._pixelated_desktop = QPixmap()
        self._pixelated_desktop_key = None
        self._path_cache = {}

    def update_context(
        self,
        desktop: QPixmap,
        selection: QRect,
        device_pixel_ratio: float,
        fallback_font_family: str,
    ) -> None:
        """Update transient paint context while retaining reusable caches."""
        desktop_key = desktop.cacheKey()
        if desktop_key != self._desktop.cacheKey():
            self._pixelated_desktop = QPixmap()
            self._pixelated_desktop_key = None
            self._path_cache.clear()
        self._desktop = desktop
        self._selection = QRect(selection)
        self._device_pixel_ratio = device_pixel_ratio
        self._fallback_font_family = fallback_font_family

    def paint(
        self,
        painter,
        annotation: dict,
        *,
        mosaic_source: QPixmap | None = None,
        mosaic_source_rect: QRect | None = None,
        eraser_source: QPixmap | None = None,
        eraser_source_rect: QRectF | None = None,
    ) -> None:
        kind = annotation["kind"]
        color = annotation["color"]
        width = annotation["width"]
        painter.save()
        painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        if kind == "rect":
            painter.drawRect(QRect(annotation["start"], annotation["end"]).normalized())
        elif kind == "ellipse":
            painter.drawEllipse(
                QRect(annotation["start"], annotation["end"]).normalized()
            )
        elif kind == "pen":
            self._paint_pen(painter, annotation)
        elif kind == "arrow":
            self.paint_arrow(
                painter,
                annotation["start"],
                annotation["end"],
                color,
                width,
            )
        elif kind == "text":
            font = painter.font()
            font.setFamily(annotation.get("font_family", self._fallback_font_family))
            font.setPixelSize(round(annotation["font_size"]))
            font.setBold(True)
            painter.setFont(font)
            text_rect = QRect(
                annotation["start"],
                annotation.get("size", QRect(0, 0, 260, 44).size()),
            )
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                annotation["text"],
            )
        elif kind == "fragment":
            painter.drawImage(
                QRect(annotation["start"], annotation["end"]).normalized(),
                annotation["image"],
            )
        elif kind == "mosaic":
            self.paint_mosaic_stroke(
                painter,
                annotation,
                source=mosaic_source,
                source_rect=mosaic_source_rect,
            )
        elif kind == "eraser":
            self.paint_eraser_stroke(
                painter,
                annotation,
                source=eraser_source,
                source_rect=eraser_source_rect,
            )
        painter.restore()

    def preview_region(self, annotation: dict) -> QRegion:
        """Return a narrow repaint region for a translated vector annotation."""
        kind = annotation["kind"]
        if kind == "pen":
            points = annotation.get("points", [])
            if len(points) >= 2 and self._is_nearly_linear(points, annotation["width"]):
                return self._line_region(points[0], points[-1], annotation["width"])
        elif kind == "arrow":
            start = annotation["start"]
            end = annotation["end"]
            region = self._line_region(start, end, annotation["width"])
            head = self._arrow_polygon(start, end, annotation["width"])
            return region.united(
                self._line_region(end, head[1], annotation["width"])
            ).united(self._line_region(end, head[2], annotation["width"]))
        elif kind in ("rect", "ellipse"):
            geometry = QRect(annotation["start"], annotation["end"]).normalized()
            padding = max(3, math.ceil(float(annotation["width"]) / 2) + 2)
            outer = geometry.adjusted(-padding, -padding, padding, padding)
            inner = geometry.adjusted(padding, padding, -padding, -padding)
            if kind == "ellipse":
                path = QPainterPath()
                path.addEllipse(QRectF(geometry))
                stroker = QPainterPathStroker()
                # Include an AA safety margin so very flat ellipses remain a
                # conservative repaint region during partial updates.
                stroker.setWidth(float(annotation["width"]) + 6.0)
                stroke = stroker.createStroke(path).toFillPolygon().toPolygon()
                return QRegion(stroke, Qt.WindingFill)
            region = QRegion(outer)
            return region.subtracted(QRegion(inner)) if inner.isValid() else region
        return QRegion(annotation_bounds(annotation))

    @staticmethod
    def _is_nearly_linear(points, width):
        start = points[0]
        end = points[-1]
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length == 0:
            return False
        tolerance = max(4.0, float(width) * 1.5)
        return all(
            abs(dx * (start.y() - points[index].y()) - (start.x() - points[index].x()) * dy)
            / length
            <= tolerance
            for index in range(1, len(points) - 1)
        )

    @staticmethod
    def _line_region(start, end, width):
        """Tile a line into a cheap QRegion without scan-converting every point."""
        padding = max(5, math.ceil(float(width) / 2) + 3)
        distance = math.hypot(end.x() - start.x(), end.y() - start.y())
        tile_size = 48
        steps = max(1, math.ceil(distance / tile_size))
        region = QRegion()
        for index in range(steps + 1):
            ratio = index / steps
            x = round(start.x() + (end.x() - start.x()) * ratio)
            y = round(start.y() + (end.y() - start.y()) * ratio)
            region = region.united(
                QRegion(
                    QRect(
                        x - tile_size // 2 - padding,
                        y - tile_size // 2 - padding,
                        tile_size + padding * 2,
                        tile_size + padding * 2,
                    )
                )
            )
        return region

    def _paint_pen(self, painter, annotation: dict) -> None:
        points = annotation.get("points", [])
        if len(points) >= 128:
            # QPainterPath's stroker becomes extremely expensive for long,
            # heavily self-intersecting paths. Bounded polylines prevent that
            # global fallback while sharing endpoints so no segment is lost.
            for polyline in self._stroke_polylines(annotation):
                painter.drawPolyline(polyline)
            return
        path = self._stroke_path(annotation)
        if not path.isEmpty():
            painter.drawPath(path)

    def _stroke_polylines(self, annotation: dict) -> list[QPolygon]:
        points = annotation.get("points", [])
        revision = annotation.get("_geometry_revision", 0)
        key = (id(annotation), "pen_polylines")
        cached = self._path_cache.get(key)
        if (
            cached is not None
            and cached["count"] == len(points)
            and cached["revision"] == revision
            and cached["first"] == points[0]
            and cached["last"] == points[-1]
        ):
            return cached["polylines"]
        polygon = points if isinstance(points, QPolygon) else QPolygon(points)
        step = self.PEN_CHUNK_SEGMENTS
        polylines = [
            polygon.mid(start, min(step + 1, len(polygon) - start))
            for start in range(0, len(polygon) - 1, step)
        ]
        self._path_cache[key] = {
            "polylines": polylines,
            "count": len(points),
            "first": QPoint(points[0]),
            "last": QPoint(points[-1]),
            "revision": revision,
        }
        return polylines

    def _stroke_path(self, annotation: dict) -> QPainterPath:
        points = annotation.get("points", [])
        revision = annotation.get("_geometry_revision", 0)
        key = (id(annotation), "pen")
        cached = self._path_cache.get(key)
        if self._can_extend_path(cached, points, revision):
            path = cached["path"]
            for index in range(cached["count"], len(points)):
                path.lineTo(points[index])
        else:
            path = QPainterPath()
            if points:
                path.moveTo(points[0])
                for index in range(1, len(points)):
                    path.lineTo(points[index])
        self._path_cache[key] = self._path_state(path, points, revision)
        return path

    def _mosaic_path(self, annotation: dict) -> QPainterPath:
        points = annotation.get("points", [])
        diameter = max(8, round(annotation["width"] * 3))
        radius = diameter // 2
        revision = annotation.get("_geometry_revision", 0)
        key = (id(annotation), "mosaic")
        cached = self._path_cache.get(key)
        can_extend = (
            self._can_extend_path(cached, points, revision)
            and cached["width"] == diameter
        )
        if can_extend:
            path = cached["path"]
            new_points = range(cached["count"], len(points))
        else:
            path = QPainterPath()
            new_points = range(len(points))
        for index in new_points:
            point = points[index]
            path.addRect(
                QRectF(
                    point.x() - radius,
                    point.y() - radius,
                    diameter,
                    diameter,
                )
            )
        # Overlapping brush rectangles must union, not cancel: the default
        # OddEvenFill rule punches holes where an even number of rects
        # overlap, which made mosaic strokes discontinuous and left striped
        # residue after erasing.
        path.setFillRule(Qt.WindingFill)
        if can_extend and cached["count"] == len(points):
            return path
        state = self._path_state(path, points, revision)
        state["width"] = diameter
        self._path_cache[key] = state
        return path

    @staticmethod
    def _can_extend_path(cached, points, revision) -> bool:
        if cached is None or not points or cached["count"] > len(points):
            return False
        if cached["first"] != points[0]:
            return False
        if cached["count"] and cached["last"] != points[cached["count"] - 1]:
            return False
        return cached["count"] < len(points) or cached["revision"] == revision

    @staticmethod
    def _path_state(path, points, revision):
        return {
            "path": path,
            "count": len(points),
            "first": QPoint(points[0]) if points else QPoint(),
            "last": QPoint(points[-1]) if points else QPoint(),
            "revision": revision,
        }

    @staticmethod
    def paint_arrow(painter, start, end, color, width) -> None:
        painter.drawLine(start, end)
        painter.setBrush(color)
        painter.drawPolygon(AnnotationRenderer._arrow_polygon(start, end, width))

    @staticmethod
    def _arrow_polygon(start, end, width) -> QPolygon:
        angle = math.atan2(start.y() - end.y(), start.x() - end.x())
        length = arrow_head_length(width)
        points = [end]
        for delta in (-0.55, 0.55):
            points.append(
                QPoint(
                    round(end.x() + math.cos(angle + delta) * length),
                    round(end.y() + math.sin(angle + delta) * length),
                )
            )
        return QPolygon(points)

    def paint_mosaic_stroke(
        self,
        painter,
        annotation: dict,
        *,
        source: QPixmap | None = None,
        source_rect: QRect | None = None,
    ) -> None:
        path = self._mosaic_path(annotation)
        source = source or self._desktop
        if path.isEmpty() or source.isNull():
            return
        pixelated = self._cached_pixelated_source(source)
        ratio = max(0.01, self._device_pixel_ratio)
        target = (
            QRectF(source_rect)
            if source_rect is not None
            else QRectF(0, 0, source.width() / ratio, source.height() / ratio)
        )
        painter.save()
        painter.setClipPath(path, Qt.IntersectClip)
        painter.drawPixmap(target, pixelated, QRectF(pixelated.rect()))
        painter.restore()

    def paint_eraser_stroke(
        self,
        painter,
        annotation: dict,
        *,
        source: QPixmap | None = None,
        source_rect: QRectF | None = None,
    ) -> None:
        path = self._mosaic_path(annotation)
        if path.isEmpty():
            return
        painter.save()
        painter.setClipPath(path, Qt.IntersectClip)
        if source is None:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillPath(path, Qt.transparent)
        elif not source.isNull():
            target = source_rect or QRectF(
                0,
                0,
                source.width() / max(0.01, self._device_pixel_ratio),
                source.height() / max(0.01, self._device_pixel_ratio),
            )
            painter.drawPixmap(target, source, QRectF(source.rect()))
        painter.restore()

    def _cached_pixelated_source(self, source: QPixmap) -> QPixmap:
        cache_key = (
            source.cacheKey(),
            round(self._device_pixel_ratio * 1000),
        )
        if (
            not self._pixelated_desktop.isNull()
            and self._pixelated_desktop_key == cache_key
        ):
            return self._pixelated_desktop
        ratio = max(0.01, self._device_pixel_ratio)
        block_size = max(1, round(self.MOSAIC_BLOCK_SIZE * ratio))
        columns = max(1, math.ceil(source.width() / block_size))
        rows = max(1, math.ceil(source.height() / block_size))
        padded_size = QSize(columns * block_size, rows * block_size)
        padded = QPixmap(padded_size)
        padded.fill(Qt.transparent)
        pad_painter = QPainter(padded)
        source_rect = QRectF(source.rect())
        pad_painter.drawPixmap(QRectF(source.rect()), source, source_rect)
        if padded.width() > source.width():
            pad_painter.drawPixmap(
                QRectF(
                    source.width(),
                    0,
                    padded.width() - source.width(),
                    source.height(),
                ),
                source,
                QRectF(source.width() - 1, 0, 1, source.height()),
            )
        if padded.height() > source.height():
            pad_painter.drawPixmap(
                QRectF(
                    0,
                    source.height(),
                    source.width(),
                    padded.height() - source.height(),
                ),
                source,
                QRectF(0, source.height() - 1, source.width(), 1),
            )
        if padded.width() > source.width() and padded.height() > source.height():
            pad_painter.drawPixmap(
                QRectF(
                    source.width(),
                    source.height(),
                    padded.width() - source.width(),
                    padded.height() - source.height(),
                ),
                source,
                QRectF(source.width() - 1, source.height() - 1, 1, 1),
            )
        pad_painter.end()
        reduced = padded.scaled(
            columns,
            rows,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        expanded = reduced.scaled(
            padded_size,
            Qt.IgnoreAspectRatio,
            Qt.FastTransformation,
        )
        self._pixelated_desktop = expanded.copy(QRect(QPoint(), source.size()))
        self._pixelated_desktop.setDevicePixelRatio(source.devicePixelRatio())
        self._pixelated_desktop_key = cache_key
        return self._pixelated_desktop

    def retain_annotations(self, annotations) -> None:
        """Release paths belonging to annotations that no longer exist."""
        live_ids = {id(annotation) for annotation in annotations}
        self._path_cache = {
            key: value for key, value in self._path_cache.items() if key[0] in live_ids
        }
