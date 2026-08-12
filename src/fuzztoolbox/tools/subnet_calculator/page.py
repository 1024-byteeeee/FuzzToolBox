import csv
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .calculator import (
    FLSMPlan,
    allocate_vlsm,
    flsm_by_count,
    network_summary,
    parse_host_requirements,
    parse_network,
    usable_range,
)
from ...core.network_info import NetworkInfo, get_network_info
from ...ui.components import configure_combo, configure_table
from fuzztoolbox.ui.style_loader import apply_style


FETCH_BATCH_SIZE = 512


class SubnetResultModel(QAbstractTableModel):
    load_state_changed = Signal()
    columns = (
        "序号",
        "需求数",
        "子网",
        "子网掩码",
        "首个可用地址",
        "最后可用地址",
        "广播/末地址",
        "可用地址数",
    )

    def __init__(self):
        super().__init__()
        self.plan = None
        self.allocations = []
        self.window_start = 0
        self.loaded_count = 0

    @property
    def total(self) -> int:
        return self.plan.total if self.plan else len(self.allocations)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.loaded_count

    def columnCount(self, _parent=QModelIndex()):
        return len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section]
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        return None

    def _row(self, row: int):
        global_index = self.window_start + row
        if self.plan:
            network = self.plan.subnet_at(global_index)
            return global_index + 1, "—", network
        allocation = self.allocations[global_index]
        return allocation.request_index, allocation.requested_hosts, allocation.network

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        if role != Qt.DisplayRole:
            return None
        sequence, requested, network = self._row(index.row())
        first, last, usable = usable_range(network)
        end_address = network.broadcast_address
        values = (
            sequence,
            requested,
            network.with_prefixlen,
            str(network.netmask),
            str(first),
            str(last),
            str(end_address),
            f"{usable:,}",
        )
        return values[index.column()]

    def set_flsm(self, plan: FLSMPlan):
        self.beginResetModel()
        self.plan = plan
        self.allocations = []
        self.window_start = 0
        self.loaded_count = min(FETCH_BATCH_SIZE, self.total)
        self.endResetModel()
        self.load_state_changed.emit()

    def set_vlsm(self, allocations: list):
        self.beginResetModel()
        self.plan = None
        self.allocations = list(allocations)
        self.window_start = 0
        self.loaded_count = len(self.allocations)
        self.endResetModel()
        self.load_state_changed.emit()

    def canFetchMore(self, parent=QModelIndex()):
        return not parent.isValid() and self.window_start + self.loaded_count < self.total

    def fetchMore(self, parent=QModelIndex()):
        if parent.isValid() or not self.canFetchMore(parent):
            return
        amount = min(
            FETCH_BATCH_SIZE,
            self.total - self.window_start - self.loaded_count,
        )
        first = self.loaded_count
        self.beginInsertRows(QModelIndex(), first, first + amount - 1)
        self.loaded_count += amount
        self.endInsertRows()
        self.load_state_changed.emit()

    def jump_to_index(self, index: int) -> int:
        if not 0 <= index < self.total:
            raise ValueError("子网序号超出范围")
        new_start = max(0, index - FETCH_BATCH_SIZE // 4)
        self.beginResetModel()
        self.window_start = new_start
        self.loaded_count = min(FETCH_BATCH_SIZE, self.total - new_start)
        self.endResetModel()
        self.load_state_changed.emit()
        return index - new_start

    def reset_window(self):
        if self.window_start == 0:
            return
        self.beginResetModel()
        self.window_start = 0
        self.loaded_count = min(FETCH_BATCH_SIZE, self.total)
        self.endResetModel()
        self.load_state_changed.emit()

    def loaded_rows(self):
        for row in range(self.rowCount()):
            yield [self.data(self.index(row, column)) for column in range(self.columnCount())]


class SubnetCalculatorPage(QWidget):
    def __init__(self, network_info: NetworkInfo = None):
        super().__init__()
        self.model = SubnetResultModel()
        self.network_info = network_info or get_network_info()
        self._column_resize_timer = QTimer(self)
        self._column_resize_timer.setSingleShot(True)
        self._column_resize_timer.timeout.connect(self._resize_result_columns)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        self.network_label = QLabel(f"本机网络  {self.network_info.display_text()}")
        self.network_label.setObjectName("networkInfo")
        apply_style(self.network_label, "tools.subnet_calculator.page:181")
        self.network_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.network_label)

        input_frame = QFrame()
        input_frame.setObjectName("calculatorPanel")
        apply_style(input_frame, "tools.subnet_calculator.page:calculator-panel")
        self.input_layout = QGridLayout(input_frame)
        self.input_layout.setContentsMargins(16, 14, 16, 14)
        self.input_layout.setHorizontalSpacing(10)
        self.input_layout.setVerticalSpacing(10)

        self.base_network = QLineEdit("192.168.1.0/24")
        self.base_network.setPlaceholderText("192.168.1.10/24、192.168.1.10/255.255.255.0 或 2001:db8::/48")
        self.mode = QComboBox()
        self.mode.addItem("等长子网划分（FLSM）", "flsm")
        self.mode.addItem("可变长子网划分（VLSM）", "vlsm")
        configure_combo(self.mode)
        self.parameter_pages = QStackedWidget()

        flsm_widget = QWidget()
        flsm_layout = QHBoxLayout(flsm_widget)
        flsm_layout.setContentsMargins(0, 0, 0, 0)
        self.flsm_basis = QComboBox()
        self.flsm_basis.addItem("按目标前缀", "prefix")
        self.flsm_basis.addItem("按子网数量", "count")
        configure_combo(self.flsm_basis)
        self.flsm_value = QLineEdit("28")
        self.flsm_value.setPlaceholderText("例如 28 或 8")
        flsm_layout.addWidget(self.flsm_basis)
        flsm_layout.addWidget(self.flsm_value, 1)

        vlsm_widget = QWidget()
        vlsm_layout = QHBoxLayout(vlsm_widget)
        vlsm_layout.setContentsMargins(0, 0, 0, 0)
        self.vlsm_requirements = QLineEdit()
        self.vlsm_requirements.setPlaceholderText("各子网地址需求，例如 120, 60, 30, 10")
        vlsm_layout.addWidget(self.vlsm_requirements)

        self.parameter_pages.addWidget(flsm_widget)
        self.parameter_pages.addWidget(vlsm_widget)
        self.calculate_button = QPushButton("计算并划分")
        self.reset_button = QPushButton("重置")
        self.reset_button.setObjectName("neutral")

        self.base_network_label = QLabel("基础网络")
        self.base_network_label.setBuddy(self.base_network)
        self.base_network_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.mode_label = QLabel("划分方式")
        self.mode_label.setBuddy(self.mode)
        self.mode_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.input_layout.addWidget(self.base_network_label, 0, 0)
        self.input_layout.addWidget(self.base_network, 0, 1, 1, 5)
        self.input_layout.addWidget(self.mode_label, 1, 0)
        self.input_layout.addWidget(self.mode, 1, 1)
        self.input_layout.addWidget(self.parameter_pages, 1, 2, 1, 2)
        self.input_layout.addWidget(self.calculate_button, 1, 4)
        self.input_layout.addWidget(self.reset_button, 1, 5)
        self.input_layout.setColumnMinimumWidth(0, 78)
        for column, stretch in ((1, 3), (2, 2), (3, 2), (4, 2), (5, 2)):
            self.input_layout.setColumnStretch(column, stretch)
        root.addWidget(input_frame)

        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("calculatorPanel")
        apply_style(self.summary_frame, "tools.subnet_calculator.page:calculator-panel")
        self.summary_grid = QGridLayout(self.summary_frame)
        self.summary_grid.setContentsMargins(16, 12, 16, 12)
        self.summary_grid.setHorizontalSpacing(14)
        self.summary_grid.setVerticalSpacing(7)
        self.summary_labels = {}
        summary_names = (
            "IP 版本",
            "规范网络",
            "前缀长度",
            "子网掩码",
            "通配符掩码",
            "网络地址",
            "广播地址",
            "首个可用地址",
            "最后可用地址",
            "地址总数",
            "可用地址数",
            "地址属性",
        )
        for index, name in enumerate(summary_names):
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            label = QLabel(f"{name}：")
            apply_style(label, "tools.subnet_calculator.page:278")
            row = index // 2
            column = (index % 2) * 2
            self.summary_grid.addWidget(label, row, column)
            self.summary_grid.addWidget(value, row, column + 1)
            self.summary_labels[name] = value
        self.summary_grid.setColumnStretch(1, 1)
        self.summary_grid.setColumnStretch(3, 1)
        root.addWidget(self.summary_frame)

        navigation = QHBoxLayout()
        self.locate_ip = QLineEdit()
        self.locate_ip.setPlaceholderText("输入 IP，定位它所属的等长子网")
        self.locate_button = QPushButton("定位")
        self.locate_button.setObjectName("secondary")
        self.reset_window_button = QPushButton("回到开头")
        self.reset_window_button.setObjectName("neutral")
        self.loaded_label = QLabel("尚未生成结果")
        self.copy_button = QPushButton("复制选中")
        self.copy_button.setObjectName("secondary")
        self.export_button = QPushButton("导出已加载结果")
        self.export_button.setObjectName("secondary")
        navigation.addWidget(self.locate_ip, 1)
        navigation.addWidget(self.locate_button)
        navigation.addWidget(self.reset_window_button)
        navigation.addWidget(self.loaded_label)
        navigation.addWidget(self.copy_button)
        navigation.addWidget(self.export_button)
        root.addLayout(navigation)

        self.table = QTableView()
        self.table.setModel(self.model)
        configure_table(self.table)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(64)
        self.table.viewport().installEventFilter(self)
        root.addWidget(self.table, 1)
        self.status = QLabel("输入基础网络并选择划分方式")
        apply_style(self.status, "tools.subnet_calculator.page:317")
        root.addWidget(self.status)

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.flsm_basis.currentIndexChanged.connect(self._basis_changed)
        self.calculate_button.clicked.connect(self.calculate)
        self.reset_button.clicked.connect(self.reset)
        self.locate_button.clicked.connect(self.locate)
        self.reset_window_button.clicked.connect(self.return_to_start)
        self.copy_button.clicked.connect(self.copy_selected)
        self.export_button.clicked.connect(self.export_loaded_results)
        self.model.load_state_changed.connect(self._update_navigation)
        self._basis_changed()
        self._update_navigation()
        self.schedule_result_column_resize()

    def showEvent(self, event):
        super().showEvent(event)
        self.schedule_result_column_resize()

    def eventFilter(self, watched, event):
        if watched is self.table.viewport() and event.type() in (QEvent.Resize, QEvent.Show):
            self.schedule_result_column_resize()
        return super().eventFilter(watched, event)

    def schedule_result_column_resize(self):
        self._column_resize_timer.start(0)

    def _resize_result_columns(self):
        if not hasattr(self, "table"):
            return
        available = max(0, self.table.viewport().width())
        ipv6 = bool(self.model.plan and self.model.plan.network.version == 6)
        if not ipv6 and self.model.allocations:
            ipv6 = self.model.allocations[0].network.version == 6
        minimums = (
            64,
            72,
            285 if ipv6 else 150,
            285 if ipv6 else 125,
            270 if ipv6 else 125,
            270 if ipv6 else 125,
            270 if ipv6 else 125,
            135,
        )
        weights = (7, 8, 18, 16, 16, 16, 16, 12)
        distributable = max(0, available - sum(minimums))
        widths = [
            minimum + distributable * weight // sum(weights)
            for minimum, weight in zip(minimums, weights)
        ]
        if sum(widths) < available:
            widths[-1] += available - sum(widths)
        for column, width in enumerate(widths):
            self.table.horizontalHeader().resizeSection(column, width)

    def _mode_changed(self):
        self.parameter_pages.setCurrentIndex(0 if self.mode.currentData() == "flsm" else 1)
        self.locate_ip.setEnabled(self.mode.currentData() == "flsm")
        self.locate_button.setEnabled(self.mode.currentData() == "flsm")

    def _basis_changed(self):
        if self.flsm_basis.currentData() == "prefix":
            self.flsm_value.setPlaceholderText("目标前缀，例如 28 或 64")
        else:
            self.flsm_value.setPlaceholderText("子网数量，例如 8")

    def calculate(self):
        try:
            network = parse_network(self.base_network.text())
            self._show_summary(network)
            if self.mode.currentData() == "flsm":
                value = int(self.flsm_value.text().strip().lstrip("/"))
                if self.flsm_basis.currentData() == "prefix":
                    plan = FLSMPlan(network, value)
                else:
                    plan = flsm_by_count(network, value)
                self.model.set_flsm(plan)
                self.status.setText(
                    f"已将 {network.with_prefixlen} 划分为 {plan.total:,} 个 /{plan.target_prefix} 子网"
                )
            else:
                requirements = parse_host_requirements(self.vlsm_requirements.text())
                allocations = allocate_vlsm(network, requirements)
                self.model.set_vlsm(allocations)
                self.status.setText(f"已完成 {len(allocations)} 个 VLSM 子网分配")
            self._update_navigation()
            self.schedule_result_column_resize()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "输入有误", str(exc))

    def _show_summary(self, network):
        for name, value in network_summary(network).items():
            self.summary_labels[name].setText(f"{value:,}" if isinstance(value, int) else str(value))

    def reset(self):
        self.base_network.setText("192.168.1.0/24")
        self.mode.setCurrentIndex(0)
        self.flsm_basis.setCurrentIndex(0)
        self.flsm_value.setText("28")
        self.vlsm_requirements.clear()
        self.locate_ip.clear()
        for label in self.summary_labels.values():
            label.setText("—")
        self.model.set_vlsm([])
        self.status.setText("输入基础网络并选择划分方式")
        self._update_navigation()

    def _update_navigation(self):
        has_results = self.model.total > 0
        if has_results:
            first = self.model.window_start + 1
            last = self.model.window_start + self.model.loaded_count
            self.loaded_label.setText(
                f"已加载 {first:,}–{last:,} / 共 {self.model.total:,} 个子网"
            )
        else:
            self.loaded_label.setText("尚未生成结果")
        self.reset_window_button.setEnabled(True)
        self.copy_button.setEnabled(has_results)
        self.export_button.setEnabled(has_results)

    def locate(self):
        if not self.model.plan:
            QMessageBox.information(self, "无法定位", "IP 定位适用于等长子网划分结果")
            return
        try:
            index = self.model.plan.index_for_ip(self.locate_ip.text())
            row = self.model.jump_to_index(index)
            self.table.clearSelection()
            self.table.setCurrentIndex(self.model.index(row, 0))
            self.table.scrollTo(self.model.index(row, 0))
            self.status.setText(
                f"{self.locate_ip.text().strip()} 位于 {self.model.plan.subnet_at(index).with_prefixlen}"
            )
        except ValueError as exc:
            QMessageBox.warning(self, "定位失败", str(exc))

    def return_to_start(self):
        self.model.reset_window()
        self.table.clearSelection()
        if self.model.rowCount() > 0:
            self.table.setCurrentIndex(self.model.index(0, 0))
        self.table.scrollToTop()

    def copy_selected(self):
        rows = sorted({index.row() for index in self.table.selectionModel().selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "未选择", "请先选择要复制的子网")
            return
        lines = ["\t".join(self.model.columns)]
        for row in rows:
            lines.append(
                "\t".join(
                    str(self.model.data(self.model.index(row, column)))
                    for column in range(self.model.columnCount())
                )
            )
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.status.setText(f"已复制 {len(rows)} 个子网")

    def export_loaded_results(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出已加载子网", "subnet-results.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".csv"
        try:
            with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(self.model.columns)
                writer.writerows(self.model.loaded_rows())
            self.status.setText(f"已导出 {self.model.loaded_count:,} 条已加载结果到 {path}")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
