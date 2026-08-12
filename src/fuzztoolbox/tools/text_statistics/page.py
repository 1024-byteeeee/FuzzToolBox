from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...ui.components import configure_combo
from ...ui.line_number_editor import LineNumberEditor
from ..text_comparer.syntax import CodeSyntaxHighlighter, LANGUAGES, detect_language
from .analyzer import analyze_text, format_report
from fuzztoolbox.ui.style_loader import apply_style


class TextStatisticsPage(QWidget):
    METRICS = (
        ("word_units", "字数"), ("characters", "字符数"),
        ("non_whitespace_characters", "非空白字符"), ("words", "单词数"),
        ("lines", "行数"), ("non_empty_lines", "非空行"),
        ("blank_lines", "空白行"), ("paragraphs", "段落数"),
        ("sentences", "句子数"), ("cjk_characters", "中日韩字符"),
        ("digits", "数字"), ("whitespace", "空白字符"),
        ("utf8_bytes", "UTF-8 字节数"), ("utf16_bytes", "UTF-16 LE 字节数"),
    )

    def __init__(self):
        super().__init__()
        self.stats = analyze_text("")
        self._build_ui()
        self.update_statistics()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)
        intro = QLabel("实时统计文本的字数、字符、单词、行数、段落与编码大小")
        apply_style(intro, "tools.text_statistics.page:33")
        root.addWidget(intro)

        actions = QHBoxLayout()
        title = QLabel("文本内容")
        apply_style(title, "tools.text_statistics.page:38")
        self.selection_status = QLabel("未选择文本")
        apply_style(self.selection_status, "tools.text_statistics.page:40")
        language_label = QLabel("代码语言")
        self.language = QComboBox()
        for label, value in LANGUAGES:
            self.language.addItem(label, value)
        configure_combo(self.language)
        self.language.setFixedWidth(130)
        self.paste_button = QPushButton("粘贴")
        self.paste_button.setObjectName("secondary")
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("neutral")
        self.copy_button = QPushButton("复制统计报告")
        self.copy_button.setObjectName("secondary")
        actions.addWidget(title)
        actions.addWidget(self.selection_status)
        actions.addStretch()
        actions.addWidget(language_label)
        actions.addWidget(self.language)
        actions.addWidget(self.paste_button)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.copy_button)
        root.addLayout(actions)

        self.input = LineNumberEditor()
        self.input.setPlaceholderText("在此输入或粘贴需要统计的文本……")
        self.input.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.input.setMinimumHeight(250)
        apply_style(self.input, "tools.text_statistics.page:67")
        root.addWidget(self.input, 1)
        self.syntax_highlighter = CodeSyntaxHighlighter(self.input.document())

        cards = QFrame()
        cards.setObjectName("statisticsCards")
        apply_style(cards, "tools.text_statistics.page:77")
        grid = QGridLayout(cards)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(9)
        self.values = {}
        for index, (key, label) in enumerate(self.METRICS):
            card = QFrame()
            card.setObjectName("statisticsCard")
            apply_style(card, "tools.text_statistics.page:85")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(2)
            caption = QLabel(label)
            apply_style(caption, "tools.text_statistics.page:92")
            value = QLabel("0")
            value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            apply_style(value, "tools.text_statistics.page:95")
            layout.addWidget(caption)
            layout.addWidget(value)
            self.values[key] = value
            grid.addWidget(card, index // 4, index % 4)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        root.addWidget(cards)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.update_statistics)
        self.syntax_detection_timer = QTimer(self)
        self.syntax_detection_timer.setSingleShot(True)
        self.syntax_detection_timer.setInterval(150)
        self.syntax_detection_timer.timeout.connect(self.update_syntax_language)
        self.input.textChanged.connect(self._text_changed)
        self.input.selectionChanged.connect(self.update_selection)
        self.language.currentIndexChanged.connect(self.update_syntax_language)
        self.paste_button.clicked.connect(self.paste_text)
        self.clear_button.clicked.connect(self.input.clear)
        self.copy_button.clicked.connect(self.copy_report)
        self.update_syntax_language()

    def _text_changed(self):
        self.timer.start()
        if self.language.currentData() == "auto":
            self.syntax_detection_timer.start()

    def update_syntax_language(self, _index=None):
        self.syntax_detection_timer.stop()
        selected = self.language.currentData()
        language = detect_language(self.input.toPlainText()) if selected == "auto" else selected
        self.syntax_highlighter.set_language(language)

    def update_statistics(self):
        self.stats = analyze_text(self.input.toPlainText())
        for key, _label in self.METRICS:
            value = getattr(self.stats, key)
            if key in {"utf8_bytes", "utf16_bytes"}:
                self.values[key].setText(f"{value:,} 字节")
            else:
                self.values[key].setText(f"{value:,}")
        self.update_selection()

    def update_selection(self):
        selected = self.input.textCursor().selectedText().replace("\u2029", "\n")
        if not selected:
            self.selection_status.setText("未选择文本")
            return
        stats = analyze_text(selected)
        self.selection_status.setText(
            f"选中：{stats.characters} 字符 · {stats.word_units} 字 · {stats.lines} 行"
        )

    def paste_text(self):
        self.input.insertPlainText(QGuiApplication.clipboard().text())
        self.input.setFocus()

    def copy_report(self):
        QGuiApplication.clipboard().setText(format_report(self.stats))
        self.selection_status.setText("统计报告已复制")
