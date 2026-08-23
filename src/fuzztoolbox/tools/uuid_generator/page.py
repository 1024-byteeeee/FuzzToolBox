import csv
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.style_loader import apply_style

from ...ui.components import configure_combo, configure_table
from .generator import UUID7Generator, UUIDFormat, generate_uuids


class UUIDResultModel(QAbstractTableModel):
    columns = ("序号", "UUID", "版本")

    def __init__(self):
        super().__init__()
        self.values = []
        self.version = 4

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.values)

    def columnCount(self, _parent=QModelIndex()):
        return len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section]
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.TextAlignmentRole:
            return Qt.AlignVCenter | (Qt.AlignLeft if index.column() == 1 else Qt.AlignCenter)
        if role == Qt.FontRole and index.column() == 1:
            return QFontDatabase.systemFont(QFontDatabase.FixedFont)
        if role != Qt.DisplayRole:
            return None
        return (f"#{index.row() + 1}", self.values[index.row()], f"v{self.version}")[index.column()]

    def set_values(self, values, version):
        self.beginResetModel()
        self.values = list(values)
        self.version = version
        self.endResetModel()

    def clear(self):
        self.set_values([], self.version)


class UUIDGeneratorPage(QWidget):
    def __init__(self):
        super().__init__()
        self.model = UUIDResultModel()
        self.uuid7_generator = UUID7Generator()
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("uuidWorkspace")
        apply_style(self, "tools.uuid_generator.page:workspace")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("uuidPageScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("uuidScrollContent")
        root = QVBoxLayout(content)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(10)
        root.setSizeConstraint(QLayout.SetMinimumSize)
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)

        panel = QFrame()
        panel.setObjectName("uuidSettingsPanel")
        form = QVBoxLayout(panel)
        form.setContentsMargins(18, 14, 18, 16)
        form.setSpacing(12)
        heading = QHBoxLayout()
        title = QLabel("生成配置")
        title.setObjectName("uuidSectionTitle")
        self.version_hint = QLabel()
        self.version_hint.setObjectName("uuidVersionHint")
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(self.version_hint)
        form.addLayout(heading)

        self.version = QComboBox()
        for label, value in (
            ("UUID v4 · 随机（推荐）", 4),
            ("UUID v7 · 时间有序", 7),
            ("UUID v1 · 时间与节点", 1),
            ("UUID v3 · 命名空间 MD5", 3),
            ("UUID v5 · 命名空间 SHA-1", 5),
        ):
            self.version.addItem(label, value)
        configure_combo(self.version)
        self.version.setMinimumWidth(220)

        self.count = QSpinBox()
        self.count.setRange(1, 100_000)
        self.count.setValue(10)
        self.count.setGroupSeparatorShown(True)
        self.count.setMinimumWidth(120)

        self.namespace = QComboBox()
        for label, value in (
            ("DNS", "dns"),
            ("URL", "url"),
            ("OID", "oid"),
            ("X.500", "x500"),
            ("自定义 UUID", "custom"),
        ):
            self.namespace.addItem(label, value)
        configure_combo(self.namespace)
        self.namespace.setMinimumWidth(120)
        self.custom_namespace = QLineEdit()
        self.custom_namespace.setPlaceholderText("输入自定义命名空间 UUID")
        self.name = QLineEdit()
        self.name.setPlaceholderText("相同命名空间和名称始终生成相同 UUID")

        self.uppercase = QCheckBox("大写")
        self.hyphens = QCheckBox("保留连字符")
        self.hyphens.setChecked(True)
        self.braces = QCheckBox("添加大括号")
        self.generate_button = QPushButton("生成 UUID")
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("neutral")

        version_label = QLabel("UUID 版本")
        version_label.setObjectName("uuidFieldLabel")
        version_label.setBuddy(self.version)
        count_label = QLabel("生成数量")
        count_label.setObjectName("uuidFieldLabel")
        count_label.setBuddy(self.count)
        settings_grid = QGridLayout()
        settings_grid.setContentsMargins(0, 0, 0, 0)
        settings_grid.setHorizontalSpacing(12)
        settings_grid.setVerticalSpacing(7)
        settings_grid.addWidget(version_label, 0, 0)
        settings_grid.addWidget(count_label, 0, 2)
        settings_grid.addWidget(self.version, 1, 0, 1, 2)
        settings_grid.addWidget(self.count, 1, 2)
        settings_grid.addWidget(self.generate_button, 1, 3)
        settings_grid.addWidget(self.clear_button, 1, 4)
        settings_grid.setColumnStretch(0, 2)
        settings_grid.setColumnStretch(1, 2)
        settings_grid.setColumnStretch(2, 1)
        form.addLayout(settings_grid)

        self.namespace_label = QLabel("命名空间")
        self.namespace_label.setBuddy(self.namespace)
        self.name_label = QLabel("名称")
        self.name_label.setBuddy(self.name)
        self.named_panel = QFrame()
        self.named_panel.setObjectName("uuidNamedPanel")
        self.named_row = QHBoxLayout(self.named_panel)
        self.named_row.setContentsMargins(12, 10, 12, 10)
        self.named_row.setSpacing(8)
        self.named_row.addWidget(self.namespace_label)
        self.named_row.addWidget(self.namespace)
        self.named_row.addWidget(self.custom_namespace, 1)
        self.named_row.addSpacing(8)
        self.named_row.addWidget(self.name_label)
        self.named_row.addWidget(self.name, 2)
        form.addWidget(self.named_panel)

        format_label = QLabel("输出格式")
        format_label.setObjectName("uuidFieldLabel")
        format_label.setBuddy(self.uppercase)
        format_panel = QFrame()
        format_panel.setObjectName("uuidFormatPanel")
        format_row = QHBoxLayout(format_panel)
        format_row.setContentsMargins(12, 8, 12, 8)
        format_row.setSpacing(22)
        format_row.addWidget(format_label)
        format_row.addWidget(self.uppercase)
        format_row.addWidget(self.hyphens)
        format_row.addWidget(self.braces)
        format_row.addStretch()
        form.addWidget(format_panel)
        root.addWidget(panel)

        results_panel = QFrame()
        results_panel.setObjectName("uuidResultsPanel")
        results_layout = QVBoxLayout(results_panel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)
        actions = QHBoxLayout()
        actions.setContentsMargins(14, 11, 14, 10)
        result_title = QLabel("生成结果")
        result_title.setObjectName("uuidSectionTitle")
        self.status = QLabel("尚未生成 UUID")
        self.status.setObjectName("uuidResultBadge")
        self.result_format = QLabel("等待生成")
        self.result_format.setObjectName("uuidResultSummary")
        self.copy_selected_button = QPushButton("复制选中")
        self.copy_all_button = QPushButton("复制全部")
        self.export_button = QPushButton("导出")
        for button in (self.copy_selected_button, self.copy_all_button, self.export_button):
            button.setObjectName("secondary")
        actions.addWidget(result_title)
        actions.addSpacing(6)
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(self.result_format)
        actions.addSpacing(6)
        actions.addWidget(self.copy_selected_button)
        actions.addSpacing(6)
        actions.addWidget(self.copy_all_button)
        actions.addSpacing(6)
        actions.addWidget(self.export_button)
        results_layout.addLayout(actions)

        self.table = QTableView()
        self.table.setObjectName("uuidResultTable")
        self.table.setMinimumHeight(440)
        self.table.setModel(self.model)
        configure_table(self.table)
        self.table.setItemDelegate(QStyledItemDelegate(self.table))
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.hide()
        header.setMinimumSectionSize(70)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(0, 72)
        header.resizeSection(2, 84)
        self.table.viewport().installEventFilter(self)
        results_layout.addWidget(self.table)
        root.addWidget(results_panel)

        self.version.currentIndexChanged.connect(self._update_namespace_inputs)
        self.namespace.currentIndexChanged.connect(self._update_namespace_inputs)
        self.generate_button.clicked.connect(self.generate)
        self.clear_button.clicked.connect(self.clear)
        self.copy_selected_button.clicked.connect(self.copy_selected)
        self.copy_all_button.clicked.connect(self.copy_all)
        self.export_button.clicked.connect(self.export_results)
        self._update_namespace_inputs()
        self.generate()

    def eventFilter(self, watched, event):
        if watched is self.table.viewport() and event.type() == QEvent.Wheel:
            scrollbar = self.table.verticalScrollBar()
            pixel_delta = event.pixelDelta().y()
            if pixel_delta:
                scrollbar.setValue(scrollbar.value() - pixel_delta)
            else:
                steps = event.angleDelta().y() / 120
                scrollbar.setValue(
                    scrollbar.value() - round(steps * scrollbar.singleStep() * 3)
                )
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _update_namespace_inputs(self):
        named = self.version.currentData() in {3, 5}
        custom = named and self.namespace.currentData() == "custom"
        hints = {
            1: "基于时间和节点信息",
            3: "命名空间 + 名称 · MD5",
            4: "安全随机 · 通用场景推荐",
            5: "命名空间 + 名称 · SHA-1",
            7: "毫秒时间有序 · 适合数据库索引",
        }
        self.version_hint.setText(hints[self.version.currentData()])
        self.named_panel.setVisible(named)
        for widget in (self.namespace_label, self.namespace, self.name_label, self.name):
            widget.setVisible(named)
        self.custom_namespace.setVisible(custom)
        if named:
            self.count.setValue(1)
        self.count.setEnabled(not named)
        self.count.setToolTip(
            "UUID v3/v5 对相同命名空间和名称只产生一个确定性结果"
            if named
            else "设置批量生成数量"
        )

    def _namespace_value(self):
        return (
            self.custom_namespace.text()
            if self.namespace.currentData() == "custom"
            else self.namespace.currentData()
        )

    def generate(self):
        version = self.version.currentData()
        options = UUIDFormat(
            uppercase=self.uppercase.isChecked(),
            hyphens=self.hyphens.isChecked(),
            braces=self.braces.isChecked(),
        )
        try:
            values = generate_uuids(
                version,
                self.count.value(),
                namespace=self._namespace_value(),
                name=self.name.text(),
                formatter=options,
                uuid7_generator=self.uuid7_generator,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "无法生成", str(exc))
            return
        self.model.set_values(values, version)
        self.status.setText(f"已生成 {len(values):,} 个 UUID v{version}")
        format_parts = [f"UUID v{version}", "大写" if options.uppercase else "小写"]
        format_parts.append("保留连字符" if options.hyphens else "无连字符")
        if options.braces:
            format_parts.append("带大括号")
        self.result_format.setText(" · ".join(format_parts))
        if values:
            self.table.selectRow(0)

    def clear(self):
        self.model.clear()
        self.status.setText("尚未生成 UUID")
        self.result_format.setText("等待生成")

    def copy_selected(self):
        rows = sorted({index.row() for index in self.table.selectionModel().selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "复制", "请先选择需要复制的 UUID")
            return
        QGuiApplication.clipboard().setText("\n".join(self.model.values[row] for row in rows))
        self.status.setText(f"已复制 {len(rows):,} 个 UUID")

    def copy_all(self):
        if not self.model.values:
            QMessageBox.information(self, "复制", "当前没有可复制的 UUID")
            return
        QGuiApplication.clipboard().setText("\n".join(self.model.values))
        self.status.setText(f"已复制全部 {len(self.model.values):,} 个 UUID")

    def export_results(self):
        if not self.model.values:
            QMessageBox.information(self, "导出", "当前没有可导出的 UUID")
            return
        filename, selected_filter = QFileDialog.getSaveFileName(
            self, "导出 UUID", "uuid-results.txt", "文本文件 (*.txt);;CSV 文件 (*.csv)"
        )
        if not filename:
            return
        path = Path(filename)
        try:
            if "CSV" in selected_filter or path.suffix.lower() == ".csv":
                if path.suffix.lower() != ".csv":
                    path = path.with_suffix(".csv")
                with path.open("w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(("序号", "UUID", "版本"))
                    writer.writerows(
                        (index, value, f"v{self.model.version}")
                        for index, value in enumerate(self.model.values, 1)
                    )
            else:
                if path.suffix.lower() != ".txt":
                    path = path.with_suffix(".txt")
                path.write_text("\n".join(self.model.values) + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.status.setText(f"已导出到 {path}")
