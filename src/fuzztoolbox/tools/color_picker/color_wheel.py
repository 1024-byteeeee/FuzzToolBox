import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class ColorWheel(QWidget):
    color_changed = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 210.0
        self._saturation = 0.75
        self._value = 1.0
        self._drag_target = None
        self._wheel_image = QImage()
        self._wheel_cache_key = None
        self.setMinimumSize(280, 280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor)

    def color(self) -> QColor:
        return QColor.fromHsvF(self._hue / 360.0, self._saturation, self._value)

    def set_color(self, color: QColor, *, emit=True) -> None:
        if not color.isValid():
            return
        hue, saturation, value, _alpha = color.getHsvF()
        if hue >= 0:
            self._hue = hue * 360.0
        self._saturation = saturation
        self._value = value
        self.update()
        if emit:
            self.color_changed.emit(self.color())

    def _geometry(self):
        side = max(1.0, min(self.width(), self.height()) - 20.0)
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        outer_radius = side / 2.0
        ring_width = max(20.0, side * 0.105)
        inner_radius = outer_radius - ring_width - 12.0
        square_half = inner_radius / math.sqrt(2.0)
        square = QRectF(
            center.x() - square_half,
            center.y() - square_half,
            square_half * 2.0,
            square_half * 2.0,
        )
        return center, outer_radius, ring_width, square

    def _ensure_wheel_image(self) -> None:
        dpr = self.devicePixelRatioF()
        cache_key = (self.size(), round(dpr, 3))
        if cache_key == self._wheel_cache_key:
            return
        pixel_width = max(1, round(self.width() * dpr))
        pixel_height = max(1, round(self.height() * dpr))
        image = QImage(pixel_width, pixel_height, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        center, outer_radius, ring_width, _square = self._geometry()
        inner_radius = outer_radius - ring_width
        for pixel_y in range(pixel_height):
            logical_y = (pixel_y + 0.5) / dpr
            dy = logical_y - center.y()
            for pixel_x in range(pixel_width):
                logical_x = (pixel_x + 0.5) / dpr
                dx = logical_x - center.x()
                radius = math.hypot(dx, dy)
                if inner_radius <= radius <= outer_radius:
                    hue = math.degrees(math.atan2(-dy, dx)) % 360.0
                    image.setPixelColor(pixel_x, pixel_y, QColor.fromHsvF(hue / 360.0, 1, 1))
        image.setDevicePixelRatio(dpr)
        self._wheel_image = image
        self._wheel_cache_key = cache_key

    def paintEvent(self, _event):
        self._ensure_wheel_image()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.drawImage(QPointF(0, 0), self._wheel_image)
        center, outer_radius, ring_width, square = self._geometry()

        painter.setPen(QPen(QColor("#dcdfe6"), 1.5))
        painter.setBrush(QColor.fromHsvF(self._hue / 360.0, 1, 1))
        painter.drawRoundedRect(square, 5, 5)

        white_gradient = QLinearGradient(square.topLeft(), square.topRight())
        white_gradient.setColorAt(0, QColor(255, 255, 255, 255))
        white_gradient.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(white_gradient)
        painter.drawRoundedRect(square, 5, 5)

        black_gradient = QLinearGradient(square.topLeft(), square.bottomLeft())
        black_gradient.setColorAt(0, QColor(0, 0, 0, 0))
        black_gradient.setColorAt(1, QColor(0, 0, 0, 255))
        painter.setBrush(black_gradient)
        painter.drawRoundedRect(square, 5, 5)

        angle = math.radians(self._hue)
        indicator_radius = outer_radius - ring_width / 2.0
        hue_point = QPointF(
            center.x() + math.cos(angle) * indicator_radius,
            center.y() - math.sin(angle) * indicator_radius,
        )
        self._draw_indicator(painter, hue_point, 8.0)
        sv_point = QPointF(
            square.left() + self._saturation * square.width(),
            square.top() + (1.0 - self._value) * square.height(),
        )
        self._draw_indicator(painter, sv_point, 7.0)

    @staticmethod
    def _draw_indicator(painter: QPainter, point: QPointF, radius: float) -> None:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 150), 4))
        painter.drawEllipse(point, radius, radius)
        painter.setPen(QPen(Qt.white, 2.5))
        painter.drawEllipse(point, radius, radius)

    def _target_at(self, point: QPointF):
        center, outer_radius, ring_width, square = self._geometry()
        radius = math.hypot(point.x() - center.x(), point.y() - center.y())
        if outer_radius - ring_width - 5 <= radius <= outer_radius + 5:
            return "hue"
        if square.adjusted(-5, -5, 5, 5).contains(point):
            return "sv"
        return None

    def _update_from_point(self, point: QPointF) -> None:
        center, _outer_radius, _ring_width, square = self._geometry()
        if self._drag_target == "hue":
            dx = point.x() - center.x()
            dy = point.y() - center.y()
            self._hue = math.degrees(math.atan2(-dy, dx)) % 360.0
        elif self._drag_target == "sv":
            self._saturation = min(1.0, max(0.0, (point.x() - square.left()) / square.width()))
            self._value = min(1.0, max(0.0, 1.0 - (point.y() - square.top()) / square.height()))
        else:
            return
        self.update()
        self.color_changed.emit(self.color())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_target = self._target_at(event.position())
            self._update_from_point(event.position())
            if self._drag_target:
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_target and event.buttons() & Qt.LeftButton:
            self._update_from_point(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_target:
            self._update_from_point(event.position())
            self._drag_target = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        self._wheel_cache_key = None
        super().resizeEvent(event)
