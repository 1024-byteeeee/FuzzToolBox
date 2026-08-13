"""Reusable controls shared by QR-based toolbox pages."""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDialog, QPushButton, QWidget

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
        self._dialog = QColorDialog(self)
        self._dialog.setWindowTitle(self.title)
        self._dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        self._refresh()

    def choose_color(self):
        self._dialog.setCurrentColor(self.color)
        # QColorDialog builds its HSV controls lazily. Reapplying the color
        # after the first layout pass prevents an uninitialized black color
        # field on the first opening on Windows.
        QTimer.singleShot(0, self._initialize_dialog)
        if self._dialog.exec() == QDialog.Accepted:
            selected = self._dialog.currentColor()
            if not selected.isValid():
                return
            self.color = QColor(selected)
            self._refresh()
            self.color_changed.emit()

    def _initialize_dialog(self):
        self._dialog.ensurePolished()
        self._dialog.setCurrentColor(self.color)
        self._dialog.update()
        for child in self._dialog.findChildren(QWidget):
            child.update()

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
