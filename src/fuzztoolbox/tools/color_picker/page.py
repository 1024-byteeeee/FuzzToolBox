from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .color_wheel import ColorWheel
from .converter import ColorValue
from fuzztoolbox.ui.style_loader import apply_style


class ColorPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor("#409EFF")
        self._alpha = 100
        self._label = "#409EFF"
        self.setMinimumHeight(92)

    def set_color(self, color: QColor, alpha: int, label: str) -> None:
        self._color = QColor(color)
        self._alpha = alpha
        self._label = label
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 8, 8)
        painter.save()
        painter.setClipPath(clip)
        tile = 12
        for row, top in enumerate(range(0, self.height(), tile)):
            for column, left in enumerate(range(0, self.width(), tile)):
                painter.fillRect(
                    left,
                    top,
                    tile,
                    tile,
                    QColor("#ffffff") if (row + column) % 2 == 0 else QColor("#dfe4ea"),
                )
        overlay = QColor(self._color)
        overlay.setAlpha(int(self._alpha * 255 / 100 + 0.5))
        painter.fillPath(clip, overlay)
        painter.restore()
        painter.setPen(QPen(QColor("#dcdfe6"), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(clip)

        composite = self._composited_rgb()
        text_color = Qt.white if self._is_dark(*composite) else QColor("#202124")
        painter.setPen(text_color)
        font = painter.font()
        font.setPointSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(bounds, Qt.AlignCenter, f"当前颜色\n{self._label}")

    def _composited_rgb(self):
        alpha = self._alpha / 100
        background = 232
        return tuple(
            channel * alpha + background * (1 - alpha)
            for channel in (self._color.red(), self._color.green(), self._color.blue())
        )

    @staticmethod
    def _is_dark(red: float, green: float, blue: float) -> bool:
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue < 145


class ColorPickerPage(QWidget):
    def __init__(self):
        super().__init__()
        self._updating = False
        self._build_ui()
        self._apply_value(ColorValue(64, 158, 255, 100))

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        intro = QLabel(
            "通过色轮选择颜色，实时查看并复制 HEX、RGB、HSL、HWB、LCH 和 CMYK"
        )
        apply_style(intro, "tools.color_picker.page:98")
        root.addWidget(intro)

        content = QHBoxLayout()
        content.setSpacing(18)

        wheel_panel = QFrame()
        wheel_panel.setObjectName("colorWheelPanel")
        apply_style(wheel_panel, "tools.color_picker.page:106")
        wheel_layout = QVBoxLayout(wheel_panel)
        wheel_layout.setContentsMargins(18, 18, 18, 18)
        self.wheel = ColorWheel()
        wheel_layout.addWidget(self.wheel, 1)
        content.addWidget(wheel_panel, 3)

        details = QFrame()
        details.setObjectName("colorDetailsPanel")
        apply_style(details, "tools.color_picker.page:118")
        details.setMinimumWidth(480)
        details.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(20, 16, 20, 16)
        detail_layout.setSpacing(10)

        self.preview = ColorPreview()
        detail_layout.addWidget(self.preview)

        channel_title = QLabel("颜色通道")
        apply_style(channel_title, "tools.color_picker.page:132")
        detail_layout.addWidget(channel_title)
        channels = QHBoxLayout()
        channels.setSpacing(10)
        channels.addStretch()
        self.red = self._channel_input("R", channels, 255)
        self.green = self._channel_input("G", channels, 255)
        self.blue = self._channel_input("B", channels, 255)
        self.alpha = self._channel_input("A", channels, 100, "%")
        channels.addStretch()
        detail_layout.addLayout(channels)

        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(10)
        opacity_label = QLabel("透明度")
        opacity_label.setFixedWidth(52)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        opacity_row.addWidget(opacity_label)
        opacity_row.addWidget(self.opacity_slider, 1)
        detail_layout.addLayout(opacity_row)

        output_title = QLabel("颜色值")
        apply_style(output_title, "tools.color_picker.page:156")
        detail_layout.addWidget(output_title)
        self.outputs = {}
        for label, key in (
            ("HEX", "hex"),
            ("RGB", "rgb"),
            ("HSL", "hsl"),
            ("HWB", "hwb"),
            ("LCH", "lch"),
            ("CMYK", "cmyk"),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            name = QLabel(label)
            name.setFixedWidth(52)
            value = QLineEdit()
            value.setReadOnly(True)
            value.setMinimumHeight(34)
            copy_button = QPushButton("复制")
            copy_button.setObjectName("secondary")
            copy_button.clicked.connect(
                lambda _checked=False, selected=key: self.copy_value(selected)
            )
            row.addWidget(name)
            row.addWidget(value, 1)
            row.addWidget(copy_button)
            detail_layout.addLayout(row)
            self.outputs[key] = value

        actions = QHBoxLayout()
        self.status = QLabel("拖动色轮或修改颜色通道")
        self.copy_all_button = QPushButton("复制全部")
        self.copy_all_button.setObjectName("secondary")
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(self.copy_all_button)
        detail_layout.addLayout(actions)
        content.addWidget(details, 2)
        root.addLayout(content, 1)

        self.wheel.color_changed.connect(self.set_color)
        for channel in (self.red, self.green, self.blue, self.alpha):
            channel.valueChanged.connect(self._set_color_from_channels)
        self.alpha.valueChanged.connect(self._sync_opacity_slider)
        self.opacity_slider.valueChanged.connect(self._set_alpha_from_slider)
        self.copy_all_button.clicked.connect(self.copy_all)

    @staticmethod
    def _channel_input(
        label: str, layout: QHBoxLayout, maximum: int, suffix: str = ""
    ) -> QSpinBox:
        name = QLabel(label)
        name.setAlignment(Qt.AlignCenter)
        name.setFixedWidth(16)
        apply_style(name, "tools.color_picker.page:210")
        value = QSpinBox()
        value.setObjectName("colorChannelInput")
        value.setRange(0, maximum)
        value.setSuffix(suffix)
        value.setButtonSymbols(QAbstractSpinBox.NoButtons)
        value.setAlignment(Qt.AlignCenter)
        value.setFixedSize(76 if suffix else 70, 38)
        apply_style(value, "tools.color_picker.page:218")
        layout.addWidget(name)
        layout.addWidget(value)
        return value

    def set_color(self, color: QColor) -> None:
        if self._updating or not color.isValid():
            return
        self._apply_value(
            ColorValue(color.red(), color.green(), color.blue(), self.alpha.value()),
            update_wheel=False,
        )

    def _set_color_from_channels(self):
        if self._updating:
            return
        self._apply_value(
            ColorValue(
                self.red.value(),
                self.green.value(),
                self.blue.value(),
                self.alpha.value(),
            )
        )

    def _apply_value(self, value: ColorValue, *, update_wheel: bool = True) -> None:
        self._updating = True
        try:
            for channel, number in (
                (self.red, value.red),
                (self.green, value.green),
                (self.blue, value.blue),
                (self.alpha, value.alpha),
            ):
                channel.blockSignals(True)
                channel.setValue(number)
                channel.blockSignals(False)
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(value.alpha)
            self.opacity_slider.blockSignals(False)
            color = QColor(value.red, value.green, value.blue)
            if update_wheel:
                self.wheel.set_color(color, emit=False)
            for key, output in self.outputs.items():
                output.setText(getattr(value, key))
            self.preview.set_color(color, value.alpha, value.hex)
        finally:
            self._updating = False

    def _sync_opacity_slider(self, alpha: int) -> None:
        if self._updating:
            return
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(alpha)
        self.opacity_slider.blockSignals(False)

    def _set_alpha_from_slider(self, alpha: int) -> None:
        if self._updating:
            return
        self.alpha.setValue(alpha)

    def copy_value(self, key: str) -> None:
        value = self.outputs[key].text()
        QGuiApplication.clipboard().setText(value)
        self.status.setText(f"已复制 {value}")

    def copy_all(self) -> None:
        text = "\n".join(
            f"{label}: {self.outputs[key].text()}"
            for label, key in (
                ("HEX", "hex"),
                ("RGB", "rgb"),
                ("HSL", "hsl"),
                ("HWB", "hwb"),
                ("LCH", "lch"),
                ("CMYK", "cmyk"),
            )
        )
        QGuiApplication.clipboard().setText(text)
        self.status.setText("已复制全部颜色值")
