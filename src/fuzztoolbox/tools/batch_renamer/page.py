"""PySide6 page for safe preview-first batch file renaming."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.components import configure_combo, configure_table
from fuzztoolbox.ui.style_loader import apply_style

from .engine import (
    RenameError,
    RenamePlan,
    RenameReceipt,
    RenameRule,
    RuleKind,
    build_plan,
    execute_plan,
    undo_receipt,
)

RULE_LABELS = {
    RuleKind.REPLACE: "查找与替换",
    RuleKind.REGEX: "正则替换",
    RuleKind.PREFIX: "添加前缀",
    RuleKind.SUFFIX: "添加后缀",
    RuleKind.NUMBER: "顺序编号",
    RuleKind.CASE: "大小写转换",
    RuleKind.REMOVE: "删除字符",
}


class RuleRow(QFrame):
    changed = Signal()
    remove_requested = Signal(object)
    move_requested = Signal(object, int)

    def __init__(self, kind=RuleKind.REPLACE, parent=None):
        super().__init__(parent)
        self.setObjectName("renameRuleRow")
        apply_style(self, "tools.batch_renamer.page:rule")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.kind = QComboBox()
        for rule_kind, label in RULE_LABELS.items():
            self.kind.addItem(label, rule_kind)
        self.kind.setCurrentIndex(self.kind.findData(kind))
        configure_combo(self.kind)
        up = QPushButton("↑")
        down = QPushButton("↓")
        remove = QPushButton("删除")
        for button in (up, down, remove):
            button.setObjectName("renameRuleAction")
        remove.setProperty("actionRole", "delete")
        header.addWidget(self.kind, 1)
        header.addWidget(up)
        header.addWidget(down)
        header.addWidget(remove)
        layout.addLayout(header)

        fields = QHBoxLayout()
        self.first = QLineEdit()
        self.second = QLineEdit()
        self.case_mode = QComboBox()
        for label, value in (
            ("大写", "upper"),
            ("小写", "lower"),
            ("标题格式", "title"),
            ("首字母大写", "capitalize"),
        ):
            self.case_mode.addItem(label, value)
        configure_combo(self.case_mode)
        fields.addWidget(self.first, 1)
        fields.addWidget(self.second, 1)
        fields.addWidget(self.case_mode, 1)
        layout.addLayout(fields)

        self.kind.currentIndexChanged.connect(self._configure_fields)
        self.kind.currentIndexChanged.connect(self.changed)
        self.first.textChanged.connect(self.changed)
        self.second.textChanged.connect(self.changed)
        self.case_mode.currentIndexChanged.connect(self.changed)
        up.clicked.connect(lambda: self.move_requested.emit(self, -1))
        down.clicked.connect(lambda: self.move_requested.emit(self, 1))
        remove.clicked.connect(lambda: self.remove_requested.emit(self))
        self._configure_fields()

    def rule(self):
        kind = self.kind.currentData()
        first = self.case_mode.currentData() if kind is RuleKind.CASE else self.first.text()
        return RenameRule(kind, first or "", self.second.text())

    def _configure_fields(self):
        kind = self.kind.currentData()
        self.first.show()
        self.second.show()
        self.case_mode.hide()
        if kind in (RuleKind.REPLACE, RuleKind.REGEX):
            self.first.setPlaceholderText("查找内容" if kind is RuleKind.REPLACE else "正则表达式")
            self.second.setPlaceholderText("替换为")
        elif kind in (RuleKind.PREFIX, RuleKind.SUFFIX):
            self.first.setPlaceholderText("前缀" if kind is RuleKind.PREFIX else "后缀")
            self.second.hide()
        elif kind is RuleKind.NUMBER:
            self.first.setPlaceholderText("起始值，默认 1")
            self.second.setPlaceholderText("位数，默认 3")
        elif kind is RuleKind.REMOVE:
            self.first.setPlaceholderText("起始位置，从 0 开始")
            self.second.setPlaceholderText("删除字符数")
        elif kind is RuleKind.CASE:
            self.first.hide()
            self.second.hide()
            self.case_mode.show()


class BatchRenamerPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.sources: list[Path] = []
        self.rule_rows: list[RuleRow] = []
        self.current_plan = RenamePlan(())
        self.last_receipt: RenameReceipt | None = None
        self._updating_table = False
        self._build_ui()
        self._add_rule(RuleKind.REPLACE)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 18)
        root.setSpacing(12)
        intro = QLabel("组合重命名规则，实时预览并安全地批量修改文件名称")
        apply_style(intro, "tools.batch_renamer.page:intro")
        root.addWidget(intro)

        source_panel = QFrame()
        source_panel.setObjectName("renameSourcePanel")
        apply_style(source_panel, "tools.batch_renamer.page:panel")
        source_layout = QHBoxLayout(source_panel)
        source_layout.setContentsMargins(16, 12, 16, 12)
        source_layout.setSpacing(10)
        self.add_files_button = QPushButton("添加文件")
        self.add_folder_button = QPushButton("添加文件夹")
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("secondary")
        self.recursive = QCheckBox("包含子文件夹")
        self.preserve_extension = QCheckBox("保护扩展名")
        self.preserve_extension.setChecked(True)
        source_layout.addWidget(self.add_files_button)
        source_layout.addWidget(self.add_folder_button)
        source_layout.addWidget(self.clear_button)
        source_layout.addSpacing(8)
        source_layout.addWidget(self.recursive)
        source_layout.addSpacing(20)
        source_layout.addWidget(self.preserve_extension)
        source_layout.addStretch()
        self.source_count = QLabel("拖入文件或选择文件夹")
        self.source_count.setObjectName("renameMuted")
        source_layout.addWidget(self.source_count)
        root.addWidget(source_panel)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        apply_style(splitter, "tools.batch_renamer.page:splitter")
        rules_panel = self._build_rules_panel()
        preview_panel = self._build_preview_panel()
        splitter.addWidget(rules_panel)
        splitter.addWidget(preview_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([410, 900])
        root.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.status = QLabel("尚未添加文件")
        self.status.setObjectName("renameStatus")
        self.undo_button = QPushButton("撤销上次重命名")
        self.undo_button.setObjectName("secondary")
        self.undo_button.setEnabled(False)
        self.rename_button = QPushButton("开始重命名")
        self.rename_button.setEnabled(False)
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(self.undo_button)
        actions.addWidget(self.rename_button)
        root.addLayout(actions)

        self.add_files_button.clicked.connect(self._choose_files)
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.clear_button.clicked.connect(self._clear_sources)
        self.recursive.toggled.connect(self._preview)
        self.preserve_extension.toggled.connect(self._preview)
        self.preview.itemChanged.connect(self._selection_changed)
        self.rename_button.clicked.connect(self._execute)
        self.undo_button.clicked.connect(self._undo)

    def _build_rules_panel(self):
        panel = QFrame()
        panel.setObjectName("renameRulesPanel")
        apply_style(panel, "tools.batch_renamer.page:panel")
        panel.setMinimumWidth(350)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("重命名规则")
        title.setObjectName("renameHeading")
        self.add_rule_type = QComboBox()
        for kind, label in RULE_LABELS.items():
            self.add_rule_type.addItem(label, kind)
        configure_combo(self.add_rule_type)
        add = QPushButton("添加规则")
        add.clicked.connect(lambda: self._add_rule(self.add_rule_type.currentData()))
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.add_rule_type)
        header.addWidget(add)
        layout.addLayout(header)
        scroll = QScrollArea()
        scroll.setObjectName("renameRulesScroll")
        apply_style(scroll, "tools.batch_renamer.page:rules-scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setObjectName("renameRulesViewport")
        apply_style(scroll.viewport(), "tools.batch_renamer.page:transparent-surface")
        self.rules_content = QWidget()
        self.rules_content.setObjectName("renameRulesContent")
        apply_style(
            self.rules_content, "tools.batch_renamer.page:transparent-surface"
        )
        self.rules_layout = QVBoxLayout(self.rules_content)
        self.rules_layout.setContentsMargins(0, 0, 0, 0)
        self.rules_layout.setSpacing(8)
        self.rules_layout.addStretch()
        scroll.setWidget(self.rules_content)
        layout.addWidget(scroll, 1)
        return panel

    def _build_preview_panel(self):
        panel = QFrame()
        panel.setObjectName("renamePreviewPanel")
        apply_style(panel, "tools.batch_renamer.page:panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("实时预览")
        title.setObjectName("renameHeading")
        self.preview_summary = QLabel("0 个文件")
        self.preview_summary.setObjectName("renameMuted")
        self.select_all_button = QPushButton("全选")
        self.invert_selection_button = QPushButton("反选")
        for button in (self.select_all_button, self.invert_selection_button):
            button.setObjectName("renameBulkAction")
            apply_style(button, "tools.batch_renamer.page:bulk-action")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.select_all_button)
        header.addWidget(self.invert_selection_button)
        header.addWidget(self.preview_summary)
        layout.addLayout(header)
        self.preview = QTableWidget(0, 4)
        self.preview.setHorizontalHeaderLabels(("选择", "原文件名", "新文件名", "状态"))
        self.preview.horizontalHeader().setStretchLastSection(False)
        configure_table(self.preview)
        header_view = self.preview.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.preview.horizontalHeaderItem(3).setSizeHint(QSize(150, 0))
        self.select_all_button.clicked.connect(self._select_all)
        self.invert_selection_button.clicked.connect(self._invert_selection)
        layout.addWidget(self.preview, 1)
        return panel

    def _set_preview_checks(self, states):
        self._updating_table = True
        try:
            for row, state in enumerate(states):
                item = self.preview.item(row, 0)
                if item is not None:
                    item.setCheckState(state)
        finally:
            self._updating_table = False
        self._preview()

    def _select_all(self):
        self._set_preview_checks(
            [Qt.Checked] * self.preview.rowCount()
        )

    def _invert_selection(self):
        self._set_preview_checks(
            [
                Qt.Unchecked
                if self.preview.item(row, 0).checkState() == Qt.Checked
                else Qt.Checked
                for row in range(self.preview.rowCount())
            ]
        )

    def _add_rule(self, kind):
        row = RuleRow(kind)
        row.changed.connect(self._preview)
        row.remove_requested.connect(self._remove_rule)
        row.move_requested.connect(self._move_rule)
        self.rule_rows.append(row)
        self.rules_layout.insertWidget(len(self.rule_rows) - 1, row)
        self._preview()

    def _remove_rule(self, row):
        if row not in self.rule_rows:
            return
        self.rule_rows.remove(row)
        row.deleteLater()
        self._preview()

    def _move_rule(self, row, offset):
        index = self.rule_rows.index(row)
        target = min(max(0, index + offset), len(self.rule_rows) - 1)
        if target == index:
            return
        self.rule_rows.pop(index)
        self.rule_rows.insert(target, row)
        self.rules_layout.removeWidget(row)
        self.rules_layout.insertWidget(target, row)
        self._preview()

    def _choose_files(self):
        paths, _filter = QFileDialog.getOpenFileNames(self, "选择要重命名的文件")
        self._add_paths(Path(path) for path in paths)

    def _choose_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if directory:
            self._add_directory(Path(directory))

    def _add_directory(self, directory):
        iterator = directory.rglob("*") if self.recursive.isChecked() else directory.iterdir()
        self._add_paths(path for path in iterator if path.is_file())

    def _add_paths(self, paths):
        known = set(self.sources)
        for path in paths:
            path = Path(path).absolute()
            if path.is_dir():
                self._add_directory(path)
            elif path.is_file() and path not in known:
                self.sources.append(path)
                known.add(path)
        self.sources.sort(key=lambda path: (str(path.parent).casefold(), path.name.casefold()))
        self.last_receipt = None
        self.undo_button.setEnabled(False)
        self._preview()

    def _clear_sources(self):
        self.sources.clear()
        self.last_receipt = None
        self.undo_button.setEnabled(False)
        self._preview()

    def _selected_sources(self):
        if self.preview.rowCount() != len(self.sources):
            return set(self.sources)
        return {
            source
            for row, source in enumerate(self.sources)
            if self.preview.item(row, 0).checkState() == Qt.Checked
        }

    def _preview(self):
        selected = self._selected_sources()
        rules = tuple(row.rule() for row in self.rule_rows)
        self.current_plan = build_plan(
            self.sources,
            rules,
            selected=selected,
            preserve_extension=self.preserve_extension.isChecked(),
        )
        self._updating_table = True
        self.preview.setRowCount(len(self.current_plan.items))
        for row, item in enumerate(self.current_plan.items):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked if item.selected else Qt.Unchecked)
            check.setTextAlignment(Qt.AlignCenter)
            original = QTableWidgetItem(item.source.name)
            target = QTableWidgetItem(item.target.name)
            if item.error:
                status_text = item.error
                color = QColor("#ff4d4f")
            elif not item.selected:
                status_text = "已排除"
                color = QColor("#8a98aa")
            elif not item.changed:
                status_text = "无变化"
                color = QColor("#8a98aa")
            else:
                status_text = "可以重命名"
                color = QColor("#19be6b")
            status = QTableWidgetItem(status_text)
            status.setForeground(color)
            status.setTextAlignment(Qt.AlignCenter)
            for column, cell in enumerate((check, original, target, status)):
                if column:
                    cell.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.preview.setItem(row, column, cell)
        self._updating_table = False
        ready = len(self.current_plan.ready_items)
        errors = len(self.current_plan.errors)
        self.source_count.setText(f"已加载 {len(self.sources)} 个文件")
        self.preview_summary.setText(
            f"{len(self.sources)} 个文件 · {ready} 项修改 · {errors} 个冲突"
        )
        self.rename_button.setEnabled(ready > 0 and errors == 0)
        if not self.sources:
            self.status.setText("尚未添加文件")
        elif errors:
            self.status.setText("请先解决预览中的冲突")
        elif ready:
            self.status.setText("预览已更新，执行前仍会再次检查磁盘状态")
        else:
            self.status.setText("当前规则没有产生名称变化")

    def _selection_changed(self, _item):
        if not self._updating_table:
            self._preview()

    def _execute(self):
        if (
            QMessageBox.question(
                self,
                "确认批量重命名",
                f"将重命名 {len(self.current_plan.ready_items)} 个文件，是否继续？",
            )
            != QMessageBox.Yes
        ):
            return
        try:
            receipt = execute_plan(self.current_plan)
        except RenameError as exc:
            QMessageBox.warning(self, "无法重命名", str(exc))
            self._preview()
            return
        self.last_receipt = receipt
        renamed = dict(receipt.mappings)
        self.sources = [renamed.get(source, source) for source in self.sources]
        self._clear_rule_rows()
        self.undo_button.setEnabled(True)
        self._preview()
        self.status.setText(f"已安全重命名 {len(receipt.mappings)} 个文件")

    def _undo(self):
        if self.last_receipt is None:
            return
        receipt = self.last_receipt
        try:
            undo_receipt(receipt)
        except RenameError as exc:
            QMessageBox.warning(self, "无法撤销", str(exc))
            return
        restored = {target: source for source, target in receipt.mappings}
        self.sources = [restored.get(source, source) for source in self.sources]
        self.last_receipt = None
        self.undo_button.setEnabled(False)
        self._preview()
        self.status.setText("已撤销上次批量重命名")

    def _clear_rule_rows(self):
        for row in self.rule_rows:
            row.deleteLater()
        self.rule_rows.clear()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        self._add_paths(
            Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()
        )
        event.acceptProposedAction()
