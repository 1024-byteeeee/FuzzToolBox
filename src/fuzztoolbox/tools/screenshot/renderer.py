"""Rendering engine for screenshot annotations."""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPen, QPixmap, QPolygon


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

    def paint(self, painter, annotation: dict) -> None:
        kind = annotation["kind"]
        color = annotation["color"]
        width = annotation["width"]
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
            self.paint_mosaic_stroke(painter, annotation)

    @staticmethod
    def _paint_pen(painter, annotation: dict) -> None:
        points = annotation.get("points", [])
        if not points:
            return
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.drawPath(path)

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

    def paint_mosaic_rect(self, painter, rect: QRect) -> None:
        rect = rect.intersected(self._selection)
        if rect.isEmpty():
            return
        ratio = self._device_pixel_ratio
        source = self._desktop.copy(
            QRect(
                round(rect.x() * ratio),
                round(rect.y() * ratio),
                round(rect.width() * ratio),
                round(rect.height() * ratio),
            )
        )
        tiny = source.scaled(
            max(1, rect.width() // 12),
            max(1, rect.height() // 12),
            Qt.IgnoreAspectRatio,
            Qt.FastTransformation,
        )
        pixelated = tiny.scaled(
            rect.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation
        )
        painter.drawPixmap(rect, pixelated)

    def paint_mosaic_stroke(self, painter, annotation: dict) -> None:
        diameter = max(8, round(annotation["width"] * 3))
        radius = diameter // 2
        for point in annotation.get("points", []):
            rect = QRect(point.x() - radius, point.y() - radius, diameter, diameter)
            painter.save()
            clip = QPainterPath()
            clip.addEllipse(QRectF(rect))
            painter.setClipPath(clip, Qt.IntersectClip)
            self.paint_mosaic_rect(painter, rect)
            painter.restore()
