from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.style_loader import apply_style

from .converter import integer_to_roman, roman_to_integer


class RomanNumeralPage(QWidget):
    def __init__(self):
        super().__init__()
        self._direction = "number"
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        intro = QLabel("在十进制整数与规范罗马数字之间进行双向转换")
        apply_style(intro, "tools.roman_numeral.page:28")
        root.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("romanPanel")
        apply_style(panel, "tools.roman_numeral.page:33")
        grid = QGridLayout(panel)
        grid.setContentsMargins(24, 22, 24, 24)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)

        number_title = QLabel("数字")
        apply_style(number_title, "tools.roman_numeral.page:46")
        roman_title = QLabel("罗马数字")
        apply_style(roman_title, "tools.roman_numeral.page:48")
        grid.addWidget(number_title, 0, 0)
        grid.addWidget(roman_title, 0, 2)

        self.number_input = QLineEdit()
        self.number_input.setPlaceholderText("输入 1–3999 之间的整数")
        self.number_input.setClearButtonEnabled(True)
        self.number_input.setMinimumHeight(44)
        self.roman_input = QLineEdit()
        self.roman_input.setPlaceholderText("例如 MMXXVI")
        self.roman_input.setClearButtonEnabled(True)
        self.roman_input.setMinimumHeight(44)
        apply_style(self.roman_input, "tools.roman_numeral.page:60")

        arrows = QVBoxLayout()
        arrows.setSpacing(8)
        self.to_roman_button = QPushButton("→")
        self.to_roman_button.setToolTip("转换为罗马数字")
        self.to_number_button = QPushButton("←")
        self.to_number_button.setToolTip("转换为数字")
        for button in (self.to_roman_button, self.to_number_button):
            button.setFixedSize(48, 38)
        arrows.addWidget(self.to_roman_button)
        arrows.addWidget(self.to_number_button)

        grid.addWidget(self.number_input, 1, 0)
        grid.addLayout(arrows, 1, 1, alignment=Qt.AlignCenter)
        grid.addWidget(self.roman_input, 1, 2)

        self.status = QLabel("输入任一格式后进行转换")
        self.status.setObjectName("romanStatus")
        apply_style(self.status, "tools.roman_numeral.page:79")
        grid.addWidget(self.status, 2, 0, 1, 3)
        root.addWidget(panel)

        actions = QHBoxLayout()
        actions.addStretch()
        self.calculate_button = QPushButton("计算")
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("neutral")
        actions.addWidget(self.calculate_button)
        actions.addWidget(self.clear_button)
        root.addLayout(actions)
        root.addStretch()

        self.number_input.returnPressed.connect(self.convert_to_roman)
        self.roman_input.returnPressed.connect(self.convert_to_number)
        self.to_roman_button.clicked.connect(self.convert_to_roman)
        self.to_number_button.clicked.connect(self.convert_to_number)
        self.number_input.textEdited.connect(self._number_edited)
        self.roman_input.textEdited.connect(self._roman_edited)
        self.calculate_button.clicked.connect(self.calculate)
        self.clear_button.clicked.connect(self.clear)

    def _number_edited(self):
        self._direction = "number"

    def _roman_edited(self):
        self._direction = "roman"

    def _show_error(self, message: str):
        self.status.setText(message)
        apply_style(self.status, "tools.roman_numeral.page:113")

    def _show_success(self, message: str):
        self.status.setText(message)
        apply_style(self.status, "tools.roman_numeral.page:120")

    def convert_to_roman(self):
        text = self.number_input.text().strip()
        try:
            if not text:
                raise ValueError("请输入数字")
            if not text.isdecimal():
                raise ValueError("请输入不含小数或符号的整数")
            number = int(text)
            roman = integer_to_roman(number)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.number_input.setText(str(number))
        self.roman_input.setText(roman)
        self._show_success(f"{number} = {roman}")

    def convert_to_number(self):
        try:
            number = roman_to_integer(self.roman_input.text())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        roman = integer_to_roman(number)
        self.roman_input.setText(roman)
        self.number_input.setText(str(number))
        self._show_success(f"{roman} = {number}")

    def calculate(self):
        if self._direction == "roman":
            self.convert_to_number()
        else:
            self.convert_to_roman()

    def clear(self):
        self.number_input.clear()
        self.roman_input.clear()
        self.status.setText("输入任一格式后进行转换")
        apply_style(self.status, "tools.roman_numeral.page:162")
        self.number_input.setFocus()
