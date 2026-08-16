from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .generator import DEFAULT_LENGTH, MAX_LENGTH, MIN_LENGTH, generate_token
from fuzztoolbox.ui.style_loader import apply_style


class TokenGeneratorPage(QWidget):
    def __init__(self):
        super().__init__()
        self.current_token = ""
        self._build_ui()
        self.generate()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        intro = QLabel("使用安全随机源和自选字符集生成长度可配置的随机 Token")
        apply_style(intro, "tools.token_generator.page:34")
        root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setObjectName("tokenScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        apply_style(scroll, "tools.token_generator.page:scroll")
        scroll_content = QWidget()
        scroll_content.setObjectName("tokenScrollContent")
        body = QVBoxLayout(scroll_content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)

        settings = QFrame()
        settings.setObjectName("tokenSettings")
        apply_style(settings, "tools.token_generator.page:39")
        form = QGridLayout(settings)
        form.setContentsMargins(22, 20, 22, 20)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(16)

        length_label = QLabel("Token 长度")
        self.length = QSpinBox()
        self.length.setRange(MIN_LENGTH, MAX_LENGTH)
        self.length.setValue(DEFAULT_LENGTH)
        self.length.setAlignment(Qt.AlignCenter)
        self.length.setFixedWidth(120)
        self.length.setSuffix(" 字符")
        length_label.setBuddy(self.length)
        form.addWidget(length_label, 0, 0)
        form.addWidget(self.length, 0, 1)

        types_label = QLabel("字符类型")
        self.lowercase = QCheckBox("小写字母  a–z")
        self.uppercase = QCheckBox("大写字母  A–Z")
        self.digits = QCheckBox("数字  0–9")
        self.symbols = QCheckBox("符号")
        self.lowercase.setChecked(True)
        self.uppercase.setChecked(True)
        self.digits.setChecked(True)
        types = QHBoxLayout()
        types.setSpacing(22)
        for checkbox in (self.lowercase, self.uppercase, self.digits, self.symbols):
            types.addWidget(checkbox)
        types.addStretch()
        form.addWidget(types_label, 1, 0, Qt.AlignTop)
        form.addLayout(types, 1, 1, 1, 2)

        custom_label = QLabel("自定义字符")
        self.custom_characters = QLineEdit()
        self.custom_characters.setPlaceholderText("可选，例如：_-.:@ ；重复字符会自动去除")
        self.custom_characters.setClearButtonEnabled(True)
        custom_label.setBuddy(self.custom_characters)
        form.addWidget(custom_label, 2, 0)
        form.addWidget(self.custom_characters, 2, 1, 1, 2)
        form.setColumnStretch(2, 1)
        body.addWidget(settings)

        result = QFrame()
        result.setObjectName("tokenResult")
        apply_style(result, "tools.token_generator.page:87")
        result_layout = QVBoxLayout(result)
        result_layout.setContentsMargins(22, 20, 22, 20)
        result_layout.setSpacing(12)
        heading = QLabel("生成结果")
        apply_style(heading, "tools.token_generator.page:95")
        result_layout.addWidget(heading)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.output.setMinimumHeight(150)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        apply_style(self.output, "tools.token_generator.page:103")
        result_layout.addWidget(self.output)

        actions = QHBoxLayout()
        self.status = QLabel("尚未生成 Token")
        apply_style(self.status, "tools.token_generator.page:112")
        self.generate_button = QPushButton("生成 Token")
        self.copy_button = QPushButton("复制")
        self.copy_button.setObjectName("secondary")
        self.generate_button.setMinimumWidth(116)
        self.copy_button.setMinimumWidth(96)
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(self.generate_button)
        actions.addWidget(self.copy_button)
        result_layout.addLayout(actions)
        body.addWidget(result)

        body.addStretch()
        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        self.generate_button.clicked.connect(self.generate)
        self.copy_button.clicked.connect(self.copy_token)
        self.length.valueChanged.connect(self._update_status_hint)

    def generate(self):
        try:
            token = generate_token(
                self.length.value(),
                lowercase=self.lowercase.isChecked(),
                uppercase=self.uppercase.isChecked(),
                digits=self.digits.isChecked(),
                symbols=self.symbols.isChecked(),
                custom_characters=self.custom_characters.text(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "无法生成", str(exc))
            return
        self.current_token = token
        self.output.setPlainText(token)
        self.status.setText(f"已生成 {len(token)} 字符的 Token")

    def copy_token(self):
        if not self.current_token:
            self.status.setText("请先生成 Token")
            return
        QGuiApplication.clipboard().setText(self.current_token)
        self.status.setText(f"已复制 {len(self.current_token)} 字符的 Token")

    def _update_status_hint(self):
        self.status.setText(f"准备生成 {self.length.value()} 字符的 Token")
