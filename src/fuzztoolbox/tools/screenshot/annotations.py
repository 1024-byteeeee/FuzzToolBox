"""Annotation state operations independent from the screenshot widget."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor


def new_annotation(
    kind: str,
    start: QPoint,
    end: QPoint,
    color: QColor,
    width: float,
    **extra,
) -> dict:
    """Create an annotation while owning all mutable Qt values."""
    annotation = {
        "kind": kind,
        "start": QPoint(start),
        "end": QPoint(end),
        "color": QColor(color),
        "width": width,
    }
    if kind in ("pen", "mosaic"):
        annotation["points"] = [QPoint(start)]
    annotation.update(extra)
    return annotation


def append_brush_points(annotation: dict, point: QPoint) -> None:
    """Interpolate a brush movement so fast pointer motion has no gaps."""
    previous = annotation["points"][-1]
    distance = math.hypot(point.x() - previous.x(), point.y() - previous.y())
    spacing = max(1.0, annotation["width"] * 0.7)
    steps = max(1, math.ceil(distance / spacing))
    for index in range(1, steps + 1):
        ratio = index / steps
        annotation["points"].append(
            QPoint(
                round(previous.x() + (point.x() - previous.x()) * ratio),
                round(previous.y() + (point.y() - previous.y()) * ratio),
            )
        )


def distance_to_segment(point: QPoint, start: QPoint, end: QPoint) -> float:
    """Return the shortest Euclidean distance to a finite line segment."""
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


def text_rect(annotation: dict) -> QRect:
    return QRect(annotation["start"], annotation["size"])


def annotation_contains(annotation: dict, point: QPoint) -> bool:
    """Hit-test a point against the visible stroke of an annotation."""
    kind = annotation["kind"]
    tolerance = max(6.0, float(annotation.get("width", 1)) + 3.0)
    if kind == "text":
        return text_rect(annotation).contains(point)
    if kind == "arrow":
        return (
            distance_to_segment(point, annotation["start"], annotation["end"])
            <= tolerance
        )
    if kind == "rect":
        rect = QRect(annotation["start"], annotation["end"]).normalized()
        rounded_tolerance = round(tolerance)
        outer = rect.adjusted(
            -rounded_tolerance,
            -rounded_tolerance,
            rounded_tolerance,
            rounded_tolerance,
        )
        inner = rect.adjusted(
            rounded_tolerance,
            rounded_tolerance,
            -rounded_tolerance,
            -rounded_tolerance,
        )
        return outer.contains(point) and (
            not inner.isValid() or not inner.contains(point)
        )
    if kind == "ellipse":
        rect = QRect(annotation["start"], annotation["end"]).normalized()
        rounded_tolerance = round(tolerance)
        outer = rect.adjusted(
            -rounded_tolerance,
            -rounded_tolerance,
            rounded_tolerance,
            rounded_tolerance,
        )
        if not outer.contains(point):
            return False
        radius_x = max(1.0, rect.width() / 2.0)
        radius_y = max(1.0, rect.height() / 2.0)
        offset_x = (point.x() - rect.center().x()) / radius_x
        offset_y = (point.y() - rect.center().y()) / radius_y
        normalized = math.hypot(offset_x, offset_y)
        return abs(normalized - 1.0) <= tolerance / min(radius_x, radius_y)
    if kind in ("pen", "mosaic"):
        points = annotation.get("points", [])
        if len(points) == 1:
            return (
                math.hypot(point.x() - points[0].x(), point.y() - points[0].y())
                <= tolerance
            )
        return any(
            distance_to_segment(point, start, end) <= tolerance
            for start, end in zip(points, points[1:])
        )
    return False


def translate_annotations(annotations: Iterable[dict], delta: QPoint) -> None:
    """Move a collection of annotations in place."""
    if delta.isNull():
        return
    for annotation in annotations:
        annotation["start"] += delta
        annotation["end"] += delta
        if "points" in annotation:
            annotation["points"] = [point + delta for point in annotation["points"]]
