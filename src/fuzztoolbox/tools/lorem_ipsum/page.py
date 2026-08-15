"""PySide6 interface for the Lorem Ipsum generator."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.style_loader import apply_style

from ..text_comparer.syntax import CodeSyntaxHighlighter
from .generator import (
    DEFAULT_PARAGRAPHS,
    DEFAULT_SENTENCES_PER_PARAGRAPH,
    DEFAULT_WORDS_PER_SENTENCE,
    PARAGRAPH_RANGE,
    SENTENCE_RANGE,
    WORD_RANGE,
    LoremResult,
    generate_lorem,
)


class SmoothIntegerSlider(QSlider):
    """Pixel-smooth slider that exposes a bounded integer result."""

    logicalValueChanged = Signal(int)
    _PRECISION = 10_000

    def __init__(self, minimum: int, maximum: int, value: int, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._logical_minimum = minimum
        self._logical_maximum = maximum
        self._last_logical_value = value
        super().setRange(0, self._PRECISION)
        span = maximum - minimum
        self.setSingleStep(max(1, self._PRECISION // max(1, span)))
        self.setPageStep(max(1, self._PRECISION // 10))
        self.setTracking(True)
        super().setValue(self._position_for(value))
        self.valueChanged.connect(self._position_changed)

    def _position_for(self, value: int) -> int:
        span = self._logical_maximum - self._logical_minimum
        return round((value - self._logical_minimum) * self._PRECISION / span)

    def logical_value(self) -> int:
        span = self._logical_maximum - self._logical_minimum
        return self._logical_minimum + round(super().value() * span / self._PRECISION)

    def _position_changed(self) -> None:
        logical = self.logical_value()
        if logical != self._last_logical_value:
            self._last_logical_value = logical
            self.logicalValueChanged.emit(logical)


class LoremIpsumPage(QWidget):
    def __init__(self):
        super().__init__()
        self.current_result: LoremResult | None = None
        self._build_ui()
        self.generate()

    def _add_slider(
        self,
        layout: QGridLayout,
        row: int,
        label: str,
        limits: tuple[int, int],
        value: int,
    ) -> tuple[SmoothIntegerSlider, QLabel]:
        title = QLabel(label)
        title.setObjectName("loremSliderTitle")
        slider = SmoothIntegerSlider(*limits, value)
        slider.setObjectName("loremSlider")
        value_label = QLabel(str(value))
        value_label.setObjectName("loremSliderValue")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setFixedWidth(54)
        slider.logicalValueChanged.connect(
            lambda current: value_label.setText(str(current))
        )
        slider.logicalValueChanged.connect(self._parameters_changed)
        layout.addWidget(title, row, 0)
        layout.addWidget(slider, row, 1)
        layout.addWidget(value_label, row, 2)
        return slider, value_label

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 18)
        root.setSpacing(12)

        intro = QLabel("生成用于排版、原型与界面设计的 Lorem Ipsum 占位文本")
        apply_style(intro, "tools.lorem_ipsum.page:intro")
        root.addWidget(intro)

        settings = QFrame()
        settings.setObjectName("loremSettings")
        apply_style(settings, "tools.lorem_ipsum.page:settings")
        form = QGridLayout(settings)
        form.setContentsMargins(20, 14, 20, 14)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        form.setColumnStretch(1, 1)

        self.paragraphs, _ = self._add_slider(
            form, 0, "段落数", PARAGRAPH_RANGE, DEFAULT_PARAGRAPHS
        )
        self.sentences, _ = self._add_slider(
            form,
            1,
            "每段句子数",
            SENTENCE_RANGE,
            DEFAULT_SENTENCES_PER_PARAGRAPH,
        )
        self.words, _ = self._add_slider(
            form, 2, "每句单词数", WORD_RANGE, DEFAULT_WORDS_PER_SENTENCE
        )

        options = QHBoxLayout()
        options.setSpacing(24)
        self.classic_opening = QCheckBox("以 Lorem ipsum 开头")
        self.classic_opening.setChecked(True)
        self.html_output = QCheckBox("HTML 格式")
        options.addWidget(self.classic_opening)
        options.addWidget(self.html_output)
        options.addStretch()
        form.addLayout(options, 3, 1, 1, 2)
        root.addWidget(settings)

        result_panel = QFrame()
        result_panel.setObjectName("loremResult")
        apply_style(result_panel, "tools.lorem_ipsum.page:result")
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(20, 14, 20, 14)
        result_layout.setSpacing(9)

        heading_row = QHBoxLayout()
        heading = QLabel("生成结果")
        heading.setObjectName("loremHeading")
        self.stats = QLabel()
        self.stats.setObjectName("loremStats")
        heading_row.addWidget(heading)
        heading_row.addStretch()
        heading_row.addWidget(self.stats)
        result_layout.addLayout(heading_row)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.output.setMinimumHeight(170)
        apply_style(self.output, "tools.lorem_ipsum.page:output")
        result_layout.addWidget(self.output, 1)
        self.output_highlighter = CodeSyntaxHighlighter(self.output.document(), "text")

        actions = QHBoxLayout()
        self.status = QLabel("准备生成")
        self.status.setObjectName("loremStatus")
        self.generate_button = QPushButton("生成")
        self.copy_button = QPushButton("复制结果")
        self.copy_button.setObjectName("secondary")
        self.generate_button.setMinimumWidth(104)
        self.copy_button.setMinimumWidth(104)
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(self.generate_button)
        actions.addWidget(self.copy_button)
        result_layout.addLayout(actions)
        root.addWidget(result_panel, 1)

        self.classic_opening.toggled.connect(self._parameters_changed)
        self.html_output.toggled.connect(self._parameters_changed)
        self.generate_button.clicked.connect(self.generate)
        self.copy_button.clicked.connect(self.copy_result)

    def _parameters_changed(self) -> None:
        self.status.setText("参数已更新，点击生成")

    def generate(self) -> None:
        self.current_result = generate_lorem(
            self.paragraphs.logical_value(),
            sentences_per_paragraph=self.sentences.logical_value(),
            words_per_sentence=self.words.logical_value(),
            start_with_lorem=self.classic_opening.isChecked(),
            html_output=self.html_output.isChecked(),
        )
        result = self.current_result
        self.output_highlighter.set_language(
            "html" if self.html_output.isChecked() else "text"
        )
        self.output.setPlainText(result.text)
        self.stats.setText(
            f"{result.word_count} 个单词 · {result.sentence_count} 个句子 · "
            f"{result.paragraph_count} 个段落 · {len(result.text)} 个字符"
        )
        self.status.setText("已生成 Lorem Ipsum 文本")

    def copy_result(self) -> None:
        if self.current_result is None:
            self.status.setText("请先生成文本")
            return
        QGuiApplication.clipboard().setText(self.current_result.text)
        self.status.setText("已复制生成结果")
