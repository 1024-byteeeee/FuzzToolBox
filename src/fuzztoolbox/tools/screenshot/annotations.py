"""Annotation state operations independent from the screenshot widget."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPoint, QRect, QSize
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
    if kind in ("pen", "mosaic", "eraser"):
        annotation["points"] = [QPoint(start)]
        annotation["_geometry_revision"] = 0
        annotation["_point_bounds"] = QRect(start, start)
        annotation["_point_bounds_count"] = 1
    annotation.update(extra)
    return annotation


def append_brush_points(annotation: dict, point: QPoint) -> None:
    """Interpolate a brush movement so fast pointer motion has no gaps."""
    previous = annotation["points"][-1]
    distance = math.hypot(point.x() - previous.x(), point.y() - previous.y())
    spacing = max(1.0, annotation["width"] * 0.7)
    steps = max(1, math.ceil(distance / spacing))
    point_bounds = _brush_point_bounds(annotation)
    for index in range(1, steps + 1):
        ratio = index / steps
        interpolated = QPoint(
            round(previous.x() + (point.x() - previous.x()) * ratio),
            round(previous.y() + (point.y() - previous.y()) * ratio),
        )
        annotation["points"].append(interpolated)
        point_bounds = point_bounds.united(QRect(interpolated, interpolated))
    annotation["_geometry_revision"] = annotation.get("_geometry_revision", 0) + 1
    annotation["_point_bounds"] = point_bounds
    annotation["_point_bounds_count"] = len(annotation["points"])


def _brush_point_bounds(annotation: dict) -> QRect:
    points = annotation.get("points", [])
    if not points:
        return QRect()
    cached = annotation.get("_point_bounds")
    if (
        isinstance(cached, QRect)
        and annotation.get("_point_bounds_count") == len(points)
    ):
        return QRect(cached)
    bounds = QRect(points[0], points[0])
    for point in points[1:]:
        bounds = bounds.united(QRect(point, point))
    annotation["_point_bounds"] = bounds
    annotation["_point_bounds_count"] = len(points)
    return QRect(bounds)


def arrow_head_length(width: float) -> float:
    """Return how far the arrow head extends beyond the end point."""
    return max(12.0, float(width) * 4)


def annotation_bounds(annotation: dict) -> QRect:
    """Return the pixels affected by an annotation, including stroke width."""
    kind = annotation["kind"]
    if kind == "text":
        bounds = text_rect(annotation)
    elif kind in ("pen", "mosaic", "eraser"):
        bounds = _brush_point_bounds(annotation)
    else:
        bounds = QRect(annotation["start"], annotation["end"]).normalized()
    if not bounds.isValid():
        return QRect()
    if kind in ("mosaic", "eraser"):
        padding = max(4, round(float(annotation.get("width", 1)) * 1.5)) + 2
    elif kind == "arrow":
        # The head polygon extends up to one head length past the end point
        # in any direction; dirty regions must cover it or old head pixels
        # are never repainted (ghosting while drawing/resizing).
        padding = math.ceil(arrow_head_length(annotation.get("width", 1))) + 2
    else:
        padding = max(2, math.ceil(float(annotation.get("width", 1)) / 2)) + 2
    return bounds.adjusted(-padding, -padding, padding, padding)


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


def annotation_geometry(annotation: dict) -> QRect:
    """Return the editable geometry without hit-test padding."""
    kind = annotation["kind"]
    if kind == "text":
        return text_rect(annotation)
    if kind in ("pen", "mosaic", "eraser"):
        return _brush_point_bounds(annotation)
    return QRect(annotation["start"], annotation["end"]).normalized()


def resize_annotation(annotation: dict, source: QRect, target: QRect) -> None:
    """Map one annotation from *source* bounds into *target* bounds."""
    if not source.isValid() or not target.isValid():
        return

    def mapped(point: QPoint) -> QPoint:
        source_width = max(1, source.width() - 1)
        source_height = max(1, source.height() - 1)
        target_width = max(0, target.width() - 1)
        target_height = max(0, target.height() - 1)
        return QPoint(
            target.left()
            + round((point.x() - source.left()) * target_width / source_width),
            target.top()
            + round((point.y() - source.top()) * target_height / source_height),
        )

    annotation["start"] = mapped(annotation["start"])
    annotation["end"] = mapped(annotation["end"])
    if "points" in annotation:
        annotation["points"] = [mapped(point) for point in annotation["points"]]
        annotation.pop("_point_bounds", None)
        annotation["_point_bounds_count"] = 0
        annotation["_geometry_revision"] = annotation.get("_geometry_revision", 0) + 1
    if annotation["kind"] == "text":
        annotation["size"] = QSize(target.width(), target.height())
        scale = min(target.width() / source.width(), target.height() / source.height())
        annotation["font_size"] = max(1.0, annotation["font_size"] * scale)


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
    if kind in ("pen", "mosaic", "eraser"):
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
            cached = annotation.get("_point_bounds")
            if isinstance(cached, QRect):
                annotation["_point_bounds"] = cached.translated(delta)
            annotation["_point_bounds_count"] = len(annotation["points"])
            annotation["_geometry_revision"] = (
                annotation.get("_geometry_revision", 0) + 1
            )
