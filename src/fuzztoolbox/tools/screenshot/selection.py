"""Pure geometry operations for screenshot selection state."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect


def handle_points(rect: QRect) -> dict[str, QPoint]:
    return {
        "tl": rect.topLeft(),
        "t": QPoint(rect.center().x(), rect.top()),
        "tr": rect.topRight(),
        "r": QPoint(rect.right(), rect.center().y()),
        "br": rect.bottomRight(),
        "b": QPoint(rect.center().x(), rect.bottom()),
        "bl": rect.bottomLeft(),
        "l": QPoint(rect.left(), rect.center().y()),
    }


def hit_handle(rect: QRect, point: QPoint, tolerance: int = 10) -> str:
    for name, handle_point in handle_points(rect).items():
        if (point - handle_point).manhattanLength() <= tolerance:
            return name
    return ""


def resize_selection(
    initial: QRect,
    handle: str,
    point: QPoint,
    bounds: QRect,
) -> QRect:
    rect = QRect(initial)
    if "l" in handle:
        rect.setLeft(point.x())
    if "r" in handle:
        rect.setRight(point.x())
    if "t" in handle:
        rect.setTop(point.y())
    if "b" in handle:
        rect.setBottom(point.y())
    return rect.normalized().intersected(bounds)


def move_selection(initial: QRect, delta: QPoint, bounds: QRect) -> QRect:
    """Translate a selection while keeping its full size inside *bounds*."""
    if not initial.isValid() or not bounds.isValid():
        return QRect(initial)
    max_x = bounds.left() + max(0, bounds.width() - initial.width())
    max_y = bounds.top() + max(0, bounds.height() - initial.height())
    desired = initial.topLeft() + delta
    x = min(max(desired.x(), bounds.left()), max_x)
    y = min(max(desired.y(), bounds.top()), max_y)
    return QRect(QPoint(x, y), initial.size())


def macos_dock_regions(geometry: QRect, available: QRect) -> list[QRect]:
    regions = []
    if available.bottom() < geometry.bottom():
        regions.append(
            QRect(
                geometry.left(),
                available.bottom() + 1,
                geometry.width(),
                geometry.bottom() - available.bottom(),
            )
        )
    if available.left() > geometry.left():
        regions.append(
            QRect(
                geometry.left(),
                geometry.top(),
                available.left() - geometry.left(),
                geometry.height(),
            )
        )
    if available.right() < geometry.right():
        regions.append(
            QRect(
                available.right() + 1,
                geometry.top(),
                geometry.right() - available.right(),
                geometry.height(),
            )
        )
    return [
        region
        for region in regions
        if region.width() >= 12 and region.height() >= 12
    ]


def unique_regions(regions) -> list[QRect]:
    result = []
    seen = set()
    for region in regions:
        values = (region.x(), region.y(), region.width(), region.height())
        if values not in seen:
            seen.add(values)
            result.append(QRect(region))
    return result
