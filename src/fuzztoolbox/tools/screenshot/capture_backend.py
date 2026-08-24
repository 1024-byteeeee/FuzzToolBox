"""Screen capture and frozen-desktop composition helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from PySide6.QtCore import QObject, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap


class ScreenCaptureCoordinator(QObject):
    """Own platform capture scheduling and report one semantic outcome."""

    ready = Signal(list)
    failed = Signal()

    def __init__(self, grabber: Callable, parent=None) -> None:
        super().__init__(parent)
        self._grabber = grabber

    def capture(self, screens: Sequence) -> None:
        if not screens:
            self.failed.emit()
            return
        # QScreen and QPixmap are GUI-thread objects on every supported Qt
        # platform.  Keep capture and pixmap decoding on the caller's GUI
        # thread; moving them into a Python worker can crash in native Qt code
        # before an exception can be reported.
        self._capture_now(tuple(screens))

    def _capture_now(self, screens: Sequence) -> None:
        try:
            shots = capture_screens(screens, self._grabber)
        except Exception:  # noqa: BLE001 - native capture failures are opaque
            self.failed.emit()
            return
        self.ready.emit(shots)


def virtual_geometry(screens: Iterable) -> QRect:
    """Return the union of all screen geometries."""
    geometry = QRect()
    for screen in screens:
        geometry = geometry.united(screen.geometry())
    return geometry


def capture_screens(screens: Iterable, grabber: Callable) -> list[tuple[QRect, QPixmap]]:
    """Capture each screen while preserving its global geometry."""
    return [(screen.geometry(), grabber(screen)) for screen in screens]


def compose_desktop(
    shots: Sequence[tuple[QRect, QPixmap]],
    geometry: QRect,
) -> tuple[QPixmap, float]:
    """Compose per-screen shots into one DPI-aware frozen desktop."""
    ratio = max((pixmap.devicePixelRatio() for _, pixmap in shots), default=1.0)
    size = geometry.size()
    desktop = QPixmap(round(size.width() * ratio), round(size.height() * ratio))
    desktop.setDevicePixelRatio(ratio)
    desktop.fill(Qt.black)
    painter = QPainter(desktop)
    for screen_geometry, pixmap in shots:
        target = QRect(
            screen_geometry.topLeft() - geometry.topLeft(), screen_geometry.size()
        )
        painter.drawPixmap(QRectF(target), pixmap, QRectF(pixmap.rect()))
    painter.end()
    return desktop, ratio
