from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...ui.components import configure_combo
from ...ui.line_number_editor import LineNumberEditor
from ..text_comparer.syntax import CodeSyntaxHighlighter
from .formatter import JSONValidationError, compact_json, format_json, parse_json
from fuzztoolbox.ui.style_loader import apply_style, set_style_state


EXAMPLE_JSON = '''{
  "name": "FuzzToolBox",
  "description": "本地桌面工具箱",
  "enabled": true,
  "tools": ["IP Scanner", "Token 生成器", "JSON 格式化器"]
}'''


class JSONFormatterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.validation_timer = QTimer(self)
        self.validation_timer.setSingleShot(True)
        self.validation_timer.setInterval(350)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        intro = QLabel("格式化、压缩并校验 JSON，错误会定位到具体行和列")
        apply_style(intro, "tools.json_formatter.page:43")
        root.addWidget(intro)

        toolbar = QFrame()
        toolbar.setObjectName("jsonToolbar")
        apply_style(toolbar, "tools.json_formatter.page:48")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 11, 14, 11)
        toolbar_layout.setSpacing(9)
        indent_label = QLabel("缩进")
        self.indent = QComboBox()
        self.indent.addItem("2 空格", 2)
        self.indent.addItem("4 空格", 4)
        self.indent.addItem("Tab", "\t")
        configure_combo(self.indent)
        self.indent.setFixedWidth(112)
        self.sort_keys = QCheckBox("按键名排序")
        self.format_button = QPushButton("格式化")
        self.compact_button = QPushButton("压缩")
        self.compact_button.setObjectName("secondary")
        self.validate_button = QPushButton("校验")
        self.validate_button.setObjectName("secondary")
        self.example_button = QPushButton("填入示例")
        self.example_button.setObjectName("neutral")
        toolbar_layout.addWidget(indent_label)
        toolbar_layout.addWidget(self.indent)
        toolbar_layout.addWidget(self.sort_keys)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.example_button)
        toolbar_layout.addWidget(self.validate_button)
        toolbar_layout.addWidget(self.compact_button)
        toolbar_layout.addWidget(self.format_button)
        root.addWidget(toolbar)

        editors = QFrame()
        editors.setObjectName("jsonEditors")
        apply_style(editors, "tools.json_formatter.page:82")
        grid = QGridLayout(editors)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        input_heading = QHBoxLayout()
        input_title = QLabel("JSON 输入")
        apply_style(input_title, "tools.json_formatter.page:95")
        self.clear_input_button = QPushButton("清空")
        self.clear_input_button.setObjectName("neutral")
        input_heading.addWidget(input_title)
        input_heading.addStretch()
        input_heading.addWidget(self.clear_input_button)
        output_heading = QHBoxLayout()
        output_title = QLabel("处理结果")
        apply_style(output_title, "tools.json_formatter.page:103")
        self.copy_button = QPushButton("复制结果")
        self.copy_button.setObjectName("secondary")
        self.clear_output_button = QPushButton("清空")
        self.clear_output_button.setObjectName("neutral")
        output_heading.addWidget(output_title)
        output_heading.addStretch()
        output_heading.addWidget(self.copy_button)
        output_heading.addWidget(self.clear_output_button)
        grid.addLayout(input_heading, 0, 0)
        grid.addLayout(output_heading, 0, 1)

        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.input = LineNumberEditor()
        self.input.setPlaceholderText('粘贴 JSON，例如：{"name":"FuzzToolBox"}')
        self.input.setFont(fixed_font)
        self.input.setTabStopDistance(self.input.fontMetrics().horizontalAdvance(" ") * 4)
        self.output = LineNumberEditor()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("格式化或压缩后的结果将在这里显示")
        self.output.setFont(fixed_font)
        for editor in (self.input, self.output):
            editor.setMinimumHeight(390)
            editor.setLineWrapMode(LineNumberEditor.NoWrap)
            apply_style(editor, "tools.json_formatter.page:127")
        grid.addWidget(self.input, 1, 0)
        grid.addWidget(self.output, 1, 1)
        self.input_highlighter = CodeSyntaxHighlighter(self.input.document(), "json")
        self.output_highlighter = CodeSyntaxHighlighter(self.output.document(), "json")
        root.addWidget(editors, 1)

        self.status = QLabel("等待输入 JSON")
        self.status.setObjectName("jsonStatus")
        self._set_status("等待输入 JSON", "neutral")
        root.addWidget(self.status)

        self.format_button.clicked.connect(self.format)
        self.compact_button.clicked.connect(self.compact)
        self.validate_button.clicked.connect(self.validate)
        self.example_button.clicked.connect(self.load_example)
        self.clear_input_button.clicked.connect(self.clear_input)
        self.clear_output_button.clicked.connect(self.clear_output)
        self.copy_button.clicked.connect(self.copy_result)
        self.input.textChanged.connect(self._schedule_live_validation)
        self.validation_timer.timeout.connect(self.validate_live)

    def _set_status(self, message: str, state: str):
        self.status.setText(message)
        set_style_state(self.status, state)

    def _source(self) -> str:
        return self.input.toPlainText()

    def _show_error(self, exc: ValueError, *, move_cursor: bool = True):
        self._set_status(str(exc), "error")
        if isinstance(exc, JSONValidationError):
            self.input.set_error_line(exc.details.line)
            if move_cursor:
                cursor = self.input.textCursor()
                cursor.setPosition(min(exc.details.position, len(self._source())))
                self.input.setTextCursor(cursor)
                self.input.setFocus()

    def _schedule_live_validation(self):
        self.input.clear_error_line()
        self.validation_timer.start()

    def validate_live(self):
        source = self._source()
        if not source.strip():
            self.input.clear_error_line()
            self._set_status("等待输入 JSON", "neutral")
            return
        try:
            value = parse_json(source)
        except ValueError as exc:
            self._show_error(exc, move_cursor=False)
            return
        self.input.clear_error_line()
        kind = "对象" if isinstance(value, dict) else "数组" if isinstance(value, list) else "值"
        self._set_status(f"实时校验通过 · 根节点类型：{kind}", "success")

    def format(self):
        self.validation_timer.stop()
        try:
            result = format_json(
                self._source(), self.indent.currentData(), sort_keys=self.sort_keys.isChecked()
            )
        except ValueError as exc:
            self._show_error(exc)
            return
        self.output.setPlainText(result)
        self.input.clear_error_line()
        self._set_status("JSON 格式化成功，语法有效", "success")

    def compact(self):
        self.validation_timer.stop()
        try:
            result = compact_json(self._source(), sort_keys=self.sort_keys.isChecked())
        except ValueError as exc:
            self._show_error(exc)
            return
        self.output.setPlainText(result)
        self.input.clear_error_line()
        self._set_status("JSON 压缩成功，语法有效", "success")

    def validate(self):
        self.validation_timer.stop()
        try:
            value = parse_json(self._source())
        except ValueError as exc:
            self._show_error(exc)
            return
        kind = "对象" if isinstance(value, dict) else "数组" if isinstance(value, list) else "值"
        self.input.clear_error_line()
        self._set_status(f"JSON 语法有效 · 根节点类型：{kind}", "success")

    def load_example(self):
        self.input.setPlainText(EXAMPLE_JSON)
        self.validation_timer.stop()
        self.output.clear()
        self._set_status("已填入示例 JSON", "neutral")
        self.input.setFocus()

    def clear_input(self):
        self.input.clear()
        self.validation_timer.stop()
        self._set_status("输入已清空", "neutral")
        self.input.setFocus()

    def clear_output(self):
        self.output.clear()
        self._set_status("结果已清空", "neutral")

    def copy_result(self):
        result = self.output.toPlainText()
        if not result:
            self._set_status("当前没有可复制的结果", "error")
            return
        QGuiApplication.clipboard().setText(result)
        self._set_status("已复制处理结果", "success")
