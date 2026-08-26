"""Rendering engine for screenshot annotations."""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen, QPixmap, QPolygon


class AnnotationRenderer:
    """Render annotations against one immutable frozen desktop image."""

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
        elif kind == "mosaic":
            self.paint_mosaic_stroke(
                painter,
                annotation,
                source=mosaic_source,
                source_rect=mosaic_source_rect,
            )
        painter.restore()

    def _paint_pen(self, painter, annotation: dict) -> None:
        path = self._stroke_path(annotation)
        if not path.isEmpty():
            painter.drawPath(path)

    def _stroke_path(self, annotation: dict) -> QPainterPath:
        points = annotation.get("points", [])
        key = (id(annotation), "pen")
        cached = self._path_cache.get(key)
        if self._can_extend_path(cached, points):
            path = cached["path"]
            for point in points[cached["count"]:]:
                path.lineTo(point)
        else:
            path = QPainterPath()
            if points:
                path.moveTo(points[0])
                for point in points[1:]:
                    path.lineTo(point)
        self._path_cache[key] = self._path_state(path, points)
        return path

    def _mosaic_path(self, annotation: dict) -> QPainterPath:
        points = annotation.get("points", [])
        diameter = max(8, round(annotation["width"] * 3))
        radius = diameter // 2
        key = (id(annotation), "mosaic")
        cached = self._path_cache.get(key)
        if (
            cached is not None
            and cached["count"] == len(points)
            and cached["width"] == diameter
            and (not points or cached["first"] == points[0])
            and (not points or cached["last"] == points[-1])
        ):
            return cached["path"]
        if len(points) == 1:
            path = QPainterPath()
            path.addEllipse(
                QRectF(
                    points[0].x() - radius,
                    points[0].y() - radius,
                    diameter,
                    diameter,
                )
            )
        else:
            centerline = self._stroke_path(annotation)
            stroker = QPainterPathStroker()
            stroker.setWidth(diameter)
            stroker.setCapStyle(Qt.RoundCap)
            stroker.setJoinStyle(Qt.RoundJoin)
            path = stroker.createStroke(centerline)
        state = self._path_state(path, points)
        state["width"] = diameter
        self._path_cache[key] = state
        return path

    @staticmethod
    def _can_extend_path(cached, points) -> bool:
        if cached is None or not points or cached["count"] > len(points):
            return False
        if cached["first"] != points[0]:
            return False
        return cached["count"] == 0 or cached["last"] == points[cached["count"] - 1]

    @staticmethod
    def _path_state(path, points):
        return {
            "path": path,
            "count": len(points),
            "first": QPoint(points[0]) if points else QPoint(),
            "last": QPoint(points[-1]) if points else QPoint(),
        }

    @staticmethod
    def paint_arrow(painter, start, end, color, width) -> None:
        painter.drawLine(start, end)
        angle = math.atan2(start.y() - end.y(), start.x() - end.x())
        length = max(12, width * 4)
        points = [end]
        for delta in (-0.55, 0.55):
            points.append(
                QPoint(
                    round(end.x() + math.cos(angle + delta) * length),
                    round(end.y() + math.sin(angle + delta) * length),
                )
            )
        painter.setBrush(color)
        painter.drawPolygon(QPolygon(points))

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
        block_size = max(1, round(12 * ratio))
        self._pixelated_desktop = source.scaled(
            max(1, source.width() // block_size),
            max(1, source.height() // block_size),
            Qt.IgnoreAspectRatio,
            Qt.FastTransformation,
        )
        self._pixelated_desktop_key = cache_key
        return self._pixelated_desktop

    def retain_annotations(self, annotations) -> None:
        """Release paths belonging to annotations that no longer exist."""
        live_ids = {id(annotation) for annotation in annotations}
        self._path_cache = {
            key: value for key, value in self._path_cache.items() if key[0] in live_ids
        }
