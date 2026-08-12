import csv
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...ui.components import configure_combo, configure_table
from .generator import UUID7Generator, UUIDFormat, generate_uuids
from fuzztoolbox.ui.style_loader import apply_style


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
            return Qt.AlignCenter
        if role != Qt.DisplayRole:
            return None
        return (index.row() + 1, self.values[index.row()], f"v{self.version}")[index.column()]

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
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        intro = QLabel("批量生成符合 RFC 标准的多版本 UUID")
        apply_style(intro, "tools.uuid_generator.page:80")
        root.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("uuidPanel")
        apply_style(panel, "tools.uuid_generator.page:85")
        form = QVBoxLayout(panel)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)

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
        version_label.setBuddy(self.version)
        count_label = QLabel("生成数量")
        count_label.setBuddy(self.count)
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(version_label)
        top_row.addWidget(self.version, 2)
        top_row.addSpacing(8)
        top_row.addWidget(count_label)
        top_row.addWidget(self.count)
        top_row.addStretch(1)
        top_row.addWidget(self.generate_button)
        top_row.addWidget(self.clear_button)
        form.addLayout(top_row)

        self.namespace_label = QLabel("命名空间")
        self.namespace_label.setBuddy(self.namespace)
        self.name_label = QLabel("名称")
        self.name_label.setBuddy(self.name)
        self.named_row = QHBoxLayout()
        self.named_row.setSpacing(8)
        self.named_row.addWidget(self.namespace_label)
        self.named_row.addWidget(self.namespace)
        self.named_row.addWidget(self.custom_namespace, 1)
        self.named_row.addSpacing(8)
        self.named_row.addWidget(self.name_label)
        self.named_row.addWidget(self.name, 2)
        form.addLayout(self.named_row)

        format_label = QLabel("输出格式")
        format_label.setBuddy(self.uppercase)
        format_row = QHBoxLayout()
        format_row.setSpacing(22)
        format_row.addWidget(format_label)
        format_row.addWidget(self.uppercase)
        format_row.addWidget(self.hyphens)
        format_row.addWidget(self.braces)
        format_row.addStretch()
        form.addLayout(format_row)
        root.addWidget(panel)

        actions = QHBoxLayout()
        self.status = QLabel("尚未生成 UUID")
        self.copy_selected_button = QPushButton("复制选中")
        self.copy_all_button = QPushButton("复制全部")
        self.export_button = QPushButton("导出")
        for button in (self.copy_selected_button, self.copy_all_button, self.export_button):
            button.setObjectName("secondary")
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(self.copy_selected_button)
        actions.addWidget(self.copy_all_button)
        actions.addWidget(self.export_button)
        root.addLayout(actions)

        self.table = QTableView()
        self.table.setModel(self.model)
        configure_table(self.table)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(70)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(0, 90)
        header.resizeSection(2, 100)
        root.addWidget(self.table, 1)

        self.version.currentIndexChanged.connect(self._update_namespace_inputs)
        self.namespace.currentIndexChanged.connect(self._update_namespace_inputs)
        self.generate_button.clicked.connect(self.generate)
        self.clear_button.clicked.connect(self.clear)
        self.copy_selected_button.clicked.connect(self.copy_selected)
        self.copy_all_button.clicked.connect(self.copy_all)
        self.export_button.clicked.connect(self.export_results)
        self._update_namespace_inputs()
        self.generate()

    def _update_namespace_inputs(self):
        named = self.version.currentData() in {3, 5}
        custom = named and self.namespace.currentData() == "custom"
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
        if values:
            self.table.selectRow(0)

    def clear(self):
        self.model.clear()
        self.status.setText("尚未生成 UUID")

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
