from pathlib import Path

from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...ui.line_number_editor import LineNumberEditor
from ...ui.style_loader import apply_style, set_style_state
from ..text_comparer.syntax import CodeSyntaxHighlighter
from .converter import convert_docker_run

EXAMPLE_COMMAND = """docker run -d \\
  --name web \\
  -p 8080:80 \\
  -e APP_ENV=production \\
  -v ./data:/usr/share/nginx/html:ro \\
  --restart unless-stopped \\
  nginx:latest"""


class DockerComposeConverterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("dockerComposeWorkspace")
        apply_style(self, "tools.docker_compose_converter.page:workspace")
        self._build_ui()
        self.load_example()
        self.convert()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setObjectName("dockerComposeContent")
        root = QVBoxLayout(content)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        intro = QLabel("将 Docker Run 命令转换为可直接编辑的 Docker Compose 配置")
        intro.setObjectName("dockerComposeIntro")
        root.addWidget(intro)

        toolbar = QFrame()
        toolbar.setObjectName("dockerComposeToolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(14, 11, 14, 11)
        bar.setSpacing(9)
        self.example_button = QPushButton("填入示例")
        self.example_button.setObjectName("neutral")
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("neutral")
        self.convert_button = QPushButton("转换")
        bar.addWidget(self.example_button)
        bar.addWidget(self.clear_button)
        bar.addStretch()
        bar.addWidget(self.convert_button)
        root.addWidget(toolbar)

        panel = QFrame()
        panel.setObjectName("dockerComposeEditors")
        grid = QGridLayout(panel)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        left = QHBoxLayout()
        left_title = QLabel("Docker Run 命令")
        left_title.setObjectName("dockerComposeSectionTitle")
        left.addWidget(left_title)
        left.addStretch()
        right = QHBoxLayout()
        right.setSpacing(9)
        right_title = QLabel("Compose YAML")
        right_title.setObjectName("dockerComposeSectionTitle")
        self.copy_button = QPushButton("复制结果")
        self.copy_button.setObjectName("secondary")
        self.save_button = QPushButton("保存文件")
        self.save_button.setObjectName("secondary")
        right.addWidget(right_title)
        right.addStretch()
        right.addWidget(self.copy_button)
        right.addWidget(self.save_button)
        grid.addLayout(left, 0, 0)
        grid.addLayout(right, 0, 1)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.input = LineNumberEditor()
        self.input.setPlaceholderText("粘贴 docker run 命令，可一次输入多条")
        self.output = LineNumberEditor()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("转换后的 compose.yaml 将显示在这里")
        for editor in (self.input, self.output):
            editor.setFont(fixed_font)
            editor.setMinimumHeight(180)
            editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            editor.setLineWrapMode(LineNumberEditor.NoWrap)
        self.input_highlighter = CodeSyntaxHighlighter(self.input.document(), "shell")
        self.output_highlighter = CodeSyntaxHighlighter(self.output.document(), "yaml")
        grid.addWidget(self.input, 1, 0)
        grid.addWidget(self.output, 1, 1)
        root.addWidget(panel)

        summary = QFrame()
        summary.setObjectName("dockerComposeSummary")
        row = QHBoxLayout(summary)
        row.setContentsMargins(14, 10, 14, 10)
        self.service_badge = QLabel("服务 0")
        self.option_badge = QLabel("已映射参数 0")
        self.note_badge = QLabel("说明 0")
        self.warning_badge = QLabel("警告 0")
        for badge in (
            self.service_badge,
            self.option_badge,
            self.note_badge,
            self.warning_badge,
        ):
            badge.setObjectName("dockerComposeBadge")
            row.addWidget(badge)
        row.addStretch()
        root.addWidget(summary)
        self.note_label = QLabel()
        self.note_label.setObjectName("dockerComposeNotes")
        self.note_label.setWordWrap(True)
        self.note_label.hide()
        root.addWidget(self.note_label)
        self.warning_label = QLabel()
        self.warning_label.setObjectName("dockerComposeWarnings")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        root.addWidget(self.warning_label)
        self.status = QLabel("等待输入命令")
        self.status.setObjectName("dockerComposeStatus")
        root.addWidget(self.status)
        root.setStretchFactor(panel, 1)
        outer.addWidget(content)

        self.convert_button.clicked.connect(self.convert)
        self.example_button.clicked.connect(self.load_example)
        self.clear_button.clicked.connect(self.clear)
        self.copy_button.clicked.connect(self.copy_result)
        self.save_button.clicked.connect(self.save_result)

    def _set_status(self, text, state):
        self.status.setText(text)
        set_style_state(self.status, state)

    def load_example(self):
        self.input.setPlainText(EXAMPLE_COMMAND)
        self._set_status("已填入示例命令", "neutral")

    def clear(self):
        self.input.clear()
        self.output.clear()
        self.note_label.hide()
        self.warning_label.hide()
        self.service_badge.setText("服务 0")
        self.option_badge.setText("已映射参数 0")
        self.note_badge.setText("说明 0")
        self.warning_badge.setText("警告 0")
        self._set_status("内容已清空", "neutral")
        self.input.setFocus()

    def convert(self):
        try:
            result = convert_docker_run(self.input.toPlainText())
        except ValueError as exc:
            self.output.clear()
            self.note_label.hide()
            self.warning_label.hide()
            self.service_badge.setText("服务 0")
            self.option_badge.setText("已映射参数 0")
            self.note_badge.setText("说明 0")
            self.warning_badge.setText("警告 0")
            self._set_status(str(exc), "error")
            return
        self.output.setPlainText(result.yaml)
        self.service_badge.setText(f"服务 {result.service_count}")
        self.option_badge.setText(f"已映射参数 {result.mapped_option_count}")
        self.note_badge.setText(f"说明 {len(result.notes)}")
        self.warning_badge.setText(f"警告 {len(result.warnings)}")
        if result.notes:
            self.note_label.setText("\n".join(result.notes))
            self.note_label.show()
        else:
            self.note_label.hide()
        if result.warnings:
            self.warning_label.setText("\n".join(result.warnings))
            self.warning_label.show()
            self._set_status("转换完成，请检查警告项", "warning")
        else:
            self.warning_label.hide()
            self._set_status("转换完成", "success")

    def copy_result(self):
        text = self.output.toPlainText()
        if not text:
            self._set_status("当前没有可复制的结果", "error")
            return
        QGuiApplication.clipboard().setText(text)
        self._set_status("已复制 Compose YAML", "success")

    def save_result(self):
        text = self.output.toPlainText()
        if not text:
            self._set_status("当前没有可保存的结果", "error")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存 Compose 文件", "compose.yaml", "YAML 文件 (*.yaml *.yml)"
        )
        if not filename:
            return
        try:
            Path(filename).write_text(text, encoding="utf-8")
        except OSError as exc:
            self._set_status(f"保存失败：{exc}", "error")
            return
        self._set_status(f"已保存到 {filename}", "success")
