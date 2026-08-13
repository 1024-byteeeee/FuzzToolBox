from PySide6.QtCore import QEvent, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyleOptionSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...ui.components import configure_combo
from ...ui.line_number_editor import LineNumberEditor
from .comparer import ComparisonResult, compare_texts, context_diff, unified_diff
from .syntax import CodeSyntaxHighlighter, LANGUAGES, detect_language
from fuzztoolbox.ui.style_loader import apply_style, set_style_state, theme_color


EXAMPLE_LEFT = """FuzzToolBox
网络工具
JSON 格式化器
旧功能说明
完成"""
EXAMPLE_RIGHT = """FuzzToolBox
网络与开发工具
JSON 格式化与校验器
Token 生成器
完成"""


class ReplaceOnInputSpinBox(QSpinBox):
    """Spin box whose compact numeric value is replaced on first click/type."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.lineEdit() and event.type() in {
            QEvent.FocusIn,
            QEvent.MouseButtonRelease,
        }:
            QTimer.singleShot(0, self.selectAll)
        return super().eventFilter(watched, event)


class TextComparerPage(QWidget):
    def __init__(self):
        super().__init__()
        self.last_result = ComparisonResult((), compare_texts("", "").stats)
        self._syncing_scroll = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)
        intro = QLabel("逐行比较两段文本，高亮新增、删除与修改，并生成标准 Diff")
        apply_style(intro, "tools.text_comparer.page:65")
        root.addWidget(intro)

        toolbar = QFrame()
        toolbar.setObjectName("textComparerToolbar")
        apply_style(toolbar, "tools.text_comparer.page:70")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(14, 11, 14, 11)
        bar.setSpacing(9)
        bar.addWidget(QLabel("显示模式"))
        self.mode = QComboBox()
        self.mode.addItem("并排对比", "side")
        self.mode.addItem("Unified Diff", "unified")
        self.mode.addItem("Context Diff", "context")
        configure_combo(self.mode)
        self.mode.setFixedWidth(150)
        bar.addWidget(self.mode)
        bar.addWidget(QLabel("代码语言"))
        self.language = QComboBox()
        for label, value in LANGUAGES:
            self.language.addItem(label, value)
        configure_combo(self.language)
        self.language.setFixedWidth(130)
        bar.addWidget(self.language)
        self.context_label = QLabel("上下文行数")
        self.context_lines = ReplaceOnInputSpinBox()
        self.context_lines.setRange(0, 20)
        self.context_lines.setValue(3)
        self.context_lines.setKeyboardTracking(False)
        self.context_lines.setAlignment(Qt.AlignCenter)
        self.context_lines.setMinimumWidth(52)
        self._resize_context_lines()
        bar.addWidget(self.context_label)
        bar.addWidget(self.context_lines)
        bar.addStretch()
        self.example_button = QPushButton("填入示例")
        self.example_button.setObjectName("neutral")
        self.swap_button = QPushButton("交换文本")
        self.swap_button.setObjectName("secondary")
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("neutral")
        self.compare_button = QPushButton("开始对比")
        for button in (self.example_button, self.swap_button, self.clear_button, self.compare_button):
            bar.addWidget(button)
        root.addWidget(toolbar)

        self.stack = QStackedWidget()
        self.side_page = QWidget()
        grid = QGridLayout(self.side_page)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        left_title = QLabel("原始文本")
        right_title = QLabel("修改后文本")
        for title in (left_title, right_title):
            apply_style(title, "tools.text_comparer.page:124")
        grid.addWidget(left_title, 0, 0)
        grid.addWidget(right_title, 0, 1)
        self.left = self._make_editor("输入原始文本")
        self.right = self._make_editor("输入修改后的文本")
        grid.addWidget(self.left, 1, 0)
        grid.addWidget(self.right, 1, 1)
        self.stack.addWidget(self.side_page)

        self.patch_output = self._make_editor("Diff 结果将在这里显示", read_only=True)
        self.patch_output.set_read_only_current_line_highlight(True)
        self.stack.addWidget(self.patch_output)
        self.left_highlighter = CodeSyntaxHighlighter(self.left.document())
        self.right_highlighter = CodeSyntaxHighlighter(self.right.document())
        self.patch_highlighter = CodeSyntaxHighlighter(self.patch_output.document())
        self.syntax_detection_timer = QTimer(self)
        self.syntax_detection_timer.setSingleShot(True)
        self.syntax_detection_timer.setInterval(150)
        self.syntax_detection_timer.timeout.connect(self._update_syntax_language)
        self._update_syntax_language()
        root.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.status = QLabel("等待输入两段文本")
        apply_style(self.status, "tools.text_comparer.page:148")
        self.legend = QWidget()
        legend_layout = QHBoxLayout(self.legend)
        legend_layout.setContentsMargins(0, 0, 0, 0)
        legend_layout.setSpacing(12)
        for text, state in (("删除", "removed"), ("新增", "added"), ("修改", "changed")):
            item = QWidget()
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(6)
            swatch = QFrame()
            swatch.setObjectName("diffLegendSwatch")
            swatch.setFixedSize(10, 10)
            set_style_state(swatch, state)
            label = QLabel(text)
            apply_style(label, "tools.text_comparer.page:162")
            item_layout.addWidget(swatch)
            item_layout.addWidget(label)
            legend_layout.addWidget(item)
        self.copy_button = QPushButton("复制 Diff")
        self.copy_button.setObjectName("secondary")
        footer.addWidget(self.status)
        footer.addStretch()
        footer.addWidget(self.legend)
        footer.addWidget(self.copy_button)
        root.addLayout(footer)

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.language.currentIndexChanged.connect(self._update_syntax_language)
        self.left.textChanged.connect(self._schedule_syntax_detection)
        self.right.textChanged.connect(self._schedule_syntax_detection)
        self.context_lines.valueChanged.connect(self._refresh_patch_if_visible)
        self.context_lines.valueChanged.connect(self._resize_context_lines)
        self.compare_button.clicked.connect(self.compare)
        self.swap_button.clicked.connect(self.swap_texts)
        self.clear_button.clicked.connect(self.clear)
        self.example_button.clicked.connect(self.load_example)
        self.copy_button.clicked.connect(self.copy_diff)
        self.left.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_scroll(self.right, value)
        )
        self.right.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_scroll(self.left, value)
        )
        self._mode_changed()

    def _resize_context_lines(self, _value=None):
        required = self.context_lines.fontMetrics().horizontalAdvance(self.context_lines.text()) + 12
        height = max(self.context_lines.sizeHint().height(), 34)
        probe_width = 120
        chrome_width = max(0, probe_width - self._context_edit_width(probe_width, height))
        width = max(52, chrome_width + required + 6)
        while width < 160 and self._context_edit_width(width, height) < required:
            width += 1
        self.context_lines.setFixedWidth(width)

    def _context_edit_width(self, width, height=None):
        option = QStyleOptionSpinBox()
        self.context_lines.initStyleOption(option)
        option.rect = QRect(0, 0, width, height or max(self.context_lines.height(), 34))
        edit_rect = self.context_lines.style().subControlRect(
            QStyle.CC_SpinBox,
            option,
            QStyle.SC_SpinBoxEditField,
            self.context_lines,
        )
        return edit_rect.width()

    def _make_editor(self, placeholder: str, read_only: bool = False) -> LineNumberEditor:
        editor = LineNumberEditor()
        editor.setPlaceholderText(placeholder)
        editor.setReadOnly(read_only)
        editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        editor.setLineWrapMode(LineNumberEditor.NoWrap)
        editor.setMinimumHeight(440)
        apply_style(editor, "tools.text_comparer.page:222")
        return editor

    def _mode_changed(self):
        patch_mode = self.mode.currentData() != "side"
        self.stack.setCurrentWidget(self.patch_output if patch_mode else self.side_page)
        self.context_label.setVisible(patch_mode)
        self.context_lines.setVisible(patch_mode)
        self.copy_button.setVisible(patch_mode)
        self.legend.setVisible(not patch_mode)
        self.patch_highlighter.set_diff_mode(self.mode.currentData() if patch_mode else None)
        if patch_mode:
            self._update_patch()

    def _update_syntax_language(self, _index=None):
        self.syntax_detection_timer.stop()
        selected = self.language.currentData()
        if selected == "auto":
            combined = "\n".join((self.left.toPlainText(), self.right.toPlainText())).strip()
            detected = detect_language(combined)
        else:
            detected = selected
        for highlighter in (self.left_highlighter, self.right_highlighter, self.patch_highlighter):
            highlighter.set_language(detected)

    def _schedule_syntax_detection(self):
        if self.language.currentData() == "auto":
            self.syntax_detection_timer.start()

    def compare(self):
        self._update_syntax_language()
        self.last_result = compare_texts(self.left.toPlainText(), self.right.toPlainText())
        self._apply_highlights()
        stats = self.last_result.stats
        if stats.identical:
            self.status.setText("两段文本完全一致")
        else:
            self.status.setText(f"新增 {stats.added} 行 · 删除 {stats.deleted} 行 · 修改 {stats.modified} 行")
        self._update_patch()

    def _line_selection(self, editor, line_number, background, spans=()):
        selections = []
        block = editor.document().findBlockByNumber(line_number - 1)
        if not block.isValid():
            return selections
        cursor = QTextCursor(block)
        line_selection = QTextEdit.ExtraSelection()
        line_selection.cursor = cursor
        line_selection.format.setBackground(QColor(background))
        line_selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selections.append(line_selection)
        for start, end in spans:
            span_cursor = QTextCursor(block)
            span_cursor.setPosition(block.position() + start)
            span_cursor.setPosition(block.position() + end, QTextCursor.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = span_cursor
            selection.format.setBackground(QColor(theme_color("diff_remove_strong" if editor is self.left else "diff_add_strong")))
            selections.append(selection)
        return selections

    def _apply_highlights(self):
        left_selections = []
        right_selections = []
        left_empty_markers = {}
        right_empty_markers = {}
        for line in self.last_result.lines:
            if line.tag == "delete" and line.left_number:
                left_selections += self._line_selection(self.left, line.left_number, theme_color("diff_remove_bg"))
                if not (line.left_text or "").strip():
                    left_empty_markers[line.left_number] = "#dc5a64"
            elif line.tag == "insert" and line.right_number:
                right_selections += self._line_selection(self.right, line.right_number, theme_color("diff_add_bg"))
                if not (line.right_text or "").strip():
                    right_empty_markers[line.right_number] = "#35a35a"
            elif line.tag == "replace":
                left_selections += self._line_selection(self.left, line.left_number, theme_color("diff_change_bg"), line.left_spans)
                right_selections += self._line_selection(self.right, line.right_number, theme_color("diff_change_bg"), line.right_spans)
                if not (line.left_text or "").strip():
                    left_empty_markers[line.left_number] = "#d79a20"
                if not (line.right_text or "").strip():
                    right_empty_markers[line.right_number] = "#d79a20"
        self.left.set_decorations(left_selections)
        self.right.set_decorations(right_selections)
        self.left.set_empty_line_markers(left_empty_markers)
        self.right.set_empty_line_markers(right_empty_markers)

    def _update_patch(self):
        mode = self.mode.currentData()
        if mode == "side":
            return
        generator = unified_diff if mode == "unified" else context_diff
        value = generator(self.left.toPlainText(), self.right.toPlainText(), self.context_lines.value())
        self.patch_output.setPlainText(value)
        self._highlight_patch(value)

    def _highlight_patch(self, value):
        selections = []
        markers = {}
        empty_markers = {}
        mode = self.mode.currentData()
        for line_number, text in enumerate(value.splitlines(), 1):
            background = marker = None
            if text.startswith("@@") or text == "***************" or text.startswith("*** ") and text.endswith(" ****"):
                background, marker = theme_color("diff_info_bg"), "#4b8fce"
            elif mode == "unified" and (text.startswith("--- ") or text.startswith("+++ ")):
                background, marker = theme_color("diff_context_bg"), "#8492a6"
            elif mode == "context" and line_number <= 2:
                background, marker = theme_color("diff_context_bg"), "#8492a6"
            elif text.startswith("+") or text.startswith("+ "):
                background, marker = theme_color("diff_add_bg"), "#35a35a"
            elif text.startswith("-") or text.startswith("- "):
                background, marker = theme_color("diff_remove_bg"), "#dc5a64"
            elif mode == "context" and text.startswith("! "):
                background, marker = theme_color("diff_change_bg"), "#d79a20"
            if not background:
                continue
            block = self.patch_output.document().findBlockByNumber(line_number - 1)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(block)
            selection.format.setBackground(QColor(background))
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selections.append(selection)
            markers[line_number] = marker
            content = text[2:] if mode == "context" and text[:2] in {"+ ", "- ", "! "} else text[1:]
            if marker in {"#35a35a", "#dc5a64", "#d79a20"} and not content.strip():
                empty_markers[line_number] = marker
        self.patch_output.set_decorations(selections)
        self.patch_output.set_line_markers(markers)
        self.patch_output.set_empty_line_markers(empty_markers)

    def _refresh_patch_if_visible(self):
        if self.mode.currentData() != "side":
            self._update_patch()

    def _sync_scroll(self, target, value):
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        target.verticalScrollBar().setValue(value)
        self._syncing_scroll = False

    def swap_texts(self):
        left, right = self.left.toPlainText(), self.right.toPlainText()
        self.left.setPlainText(right)
        self.right.setPlainText(left)
        self.compare()

    def load_example(self):
        self.left.setPlainText(EXAMPLE_LEFT)
        self.right.setPlainText(EXAMPLE_RIGHT)
        self.compare()

    def clear(self):
        self.left.clear()
        self.right.clear()
        self.patch_output.clear()
        self.patch_output.clear_line_markers()
        self.left.clear_empty_line_markers()
        self.right.clear_empty_line_markers()
        self.patch_output.clear_empty_line_markers()
        self.left.clear_decorations()
        self.right.clear_decorations()
        self.status.setText("等待输入两段文本")
        self.left.setFocus()

    def copy_diff(self):
        value = self.patch_output.toPlainText()
        if not value:
            self.status.setText("当前没有可复制的 Diff")
            return
        QGuiApplication.clipboard().setText(value)
        self.status.setText("已复制 Diff")
