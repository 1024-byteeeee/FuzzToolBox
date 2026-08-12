"""Reusable controls shared by QR-based toolbox pages."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QPushButton

from fuzztoolbox.ui.style_loader import apply_style


class ColorButton(QPushButton):
    color_changed = Signal()

    def __init__(self, color: str, title: str):
        super().__init__()
        self.color = QColor(color)
        self.title = title
        self.setObjectName("colorPicker")
        self.setMinimumWidth(128)
        self.clicked.connect(self.choose_color)
        self._refresh()

    def choose_color(self):
        selected = QColorDialog.getColor(self.color, self, self.title)
        if selected.isValid():
            self.color = selected
            self._refresh()
            self.color_changed.emit()

    def _refresh(self):
        value = self.color.name().upper()
        luminance = (
            self.color.red() * 299 + self.color.green() * 587 + self.color.blue() * 114
        ) / 1000
        text_color = "#303133" if luminance > 155 else "#ffffff"
        hover = self.color.lighter(108).name()
        self.setText(f"●  {value}")
        apply_style(
            self,
            "tools.qr_generator.components:color-picker",
            value=value,
            text_color=text_color,
            hover=hover,
        )
