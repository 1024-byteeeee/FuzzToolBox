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
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.style_loader import apply_style

from ...core.network_info import NetworkInfo, get_network_info
from ...ui.components import configure_combo, configure_table
from .calculator import (
    FLSMPlan,
    allocate_vlsm,
    flsm_by_count,
    network_summary,
    parse_host_requirements,
    parse_network,
    usable_range,
)

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

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else self.loaded_count

    def columnCount(self, _parent=None):
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

    def canFetchMore(self, parent=None):
        parent_is_valid = parent is not None and parent.isValid()
        return not parent_is_valid and self.window_start + self.loaded_count < self.total

    def fetchMore(self, parent=None):
        if parent is not None and parent.isValid() or not self.canFetchMore(parent):
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
        self.setObjectName("subnetWorkspace")
        apply_style(self, "tools.subnet_calculator.page:workspace")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("subnetPageScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_content = QWidget()
        scroll_content.setObjectName("subnetScrollContent")
        root = QVBoxLayout(scroll_content)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(10)
        root.setSizeConstraint(QLayout.SetMinimumSize)
        self.scroll_area.setWidget(scroll_content)
        outer.addWidget(self.scroll_area)

        self.network_label = QLabel(f"本机网络  {self.network_info.display_text()}")
        self.network_label.setObjectName("networkInfo")
        self.network_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.network_label)

        input_frame = QFrame()
        input_frame.setObjectName("subnetInputPanel")
        input_panel_layout = QVBoxLayout(input_frame)
        input_panel_layout.setContentsMargins(18, 14, 18, 16)
        input_panel_layout.setSpacing(11)
        input_heading = QHBoxLayout()
        input_title = QLabel("规划参数")
        input_title.setObjectName("subnetSectionTitle")
        input_hint = QLabel("支持 IPv4 / IPv6 · FLSM / VLSM")
        input_hint.setObjectName("subnetSectionHint")
        input_heading.addWidget(input_title)
        input_heading.addStretch()
        input_heading.addWidget(input_hint)
        input_panel_layout.addLayout(input_heading)

        self.input_layout = QGridLayout()
        self.input_layout.setContentsMargins(0, 0, 0, 0)
        self.input_layout.setHorizontalSpacing(12)
        self.input_layout.setVerticalSpacing(8)

        self.base_network = QLineEdit("192.168.1.0/24")
        self.base_network.setPlaceholderText("192.168.1.10/24、192.168.1.10/255.255.255.0 或 2001:db8::/48")
        self.mode = QComboBox()
        self.mode.addItem("可变长子网划分（VLSM）", "vlsm")
        self.mode.addItem("等长子网划分（FLSM）", "flsm")
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
        self.vlsm_requirements.setText("120, 60, 30, 10")
        vlsm_layout.addWidget(self.vlsm_requirements)

        self.parameter_pages.addWidget(flsm_widget)
        self.parameter_pages.addWidget(vlsm_widget)
        self.calculate_button = QPushButton("开始计算")
        self.calculate_button.setMinimumWidth(112)
        self.reset_button = QPushButton("重置")
        self.reset_button.setObjectName("neutral")

        self.base_network_label = QLabel("基础网络")
        self.base_network_label.setBuddy(self.base_network)
        self.base_network_label.setObjectName("subnetFieldLabel")
        self.mode_label = QLabel("划分方式")
        self.mode_label.setBuddy(self.mode)
        self.mode_label.setObjectName("subnetFieldLabel")
        parameter_label = QLabel("划分参数")
        parameter_label.setObjectName("subnetFieldLabel")
        self.input_layout.addWidget(self.base_network_label, 0, 0)
        self.input_layout.addWidget(self.base_network, 1, 0, 1, 3)
        self.input_layout.addWidget(self.mode_label, 0, 3)
        self.input_layout.addWidget(self.mode, 1, 3, 1, 2)
        self.input_layout.addWidget(parameter_label, 2, 0)
        self.input_layout.addWidget(self.parameter_pages, 3, 0, 1, 3)
        self.input_layout.addWidget(self.calculate_button, 3, 3)
        self.input_layout.addWidget(self.reset_button, 3, 4)
        for column, stretch in ((0, 2), (1, 2), (2, 2), (3, 2), (4, 1)):
            self.input_layout.setColumnStretch(column, stretch)
        input_panel_layout.addLayout(self.input_layout)
        root.addWidget(input_frame)

        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("subnetSummaryPanel")
        summary_layout = QVBoxLayout(self.summary_frame)
        summary_layout.setContentsMargins(16, 12, 16, 14)
        summary_layout.setSpacing(10)
        summary_heading = QHBoxLayout()
        summary_title = QLabel("网络概览")
        summary_title.setObjectName("subnetSectionTitle")
        self.summary_network = QLabel("等待计算")
        self.summary_network.setObjectName("subnetSummaryNetwork")
        self.summary_network.setTextInteractionFlags(Qt.TextSelectableByMouse)
        summary_heading.addWidget(summary_title)
        summary_heading.addStretch()
        summary_heading.addWidget(self.summary_network)
        summary_layout.addLayout(summary_heading)

        metrics = QHBoxLayout()
        metrics.setSpacing(9)
        self.metric_values = {}
        for name in ("规划模式", "子网数量", "前缀规划", "可用容量"):
            card = QFrame()
            card.setObjectName("subnetMetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 9)
            card_layout.setSpacing(3)
            title = QLabel(name)
            title.setObjectName("subnetMetricTitle")
            value = QLabel("—")
            value.setObjectName("subnetMetricValue")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            metrics.addWidget(card, 1)
            self.metric_values[name] = value
        summary_layout.addLayout(metrics)

        details = QFrame()
        details.setObjectName("subnetDetailStrip")
        self.summary_grid = QGridLayout(details)
        self.summary_grid.setContentsMargins(12, 8, 12, 8)
        self.summary_grid.setHorizontalSpacing(12)
        self.summary_grid.setVerticalSpacing(5)
        self.summary_labels = {}
        summary_names = (
            "子网掩码",
            "通配符掩码",
            "网络地址",
            "广播地址",
            "首个可用地址",
            "最后可用地址",
            "地址总数",
            "可用地址数",
        )
        for index, name in enumerate(summary_names):
            value = QLabel("—")
            value.setObjectName("subnetDetailValue")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            label = QLabel(f"{name}：")
            label.setObjectName("subnetDetailLabel")
            row = index // 2
            column = (index % 2) * 2
            self.summary_grid.addWidget(label, row, column)
            self.summary_grid.addWidget(value, row, column + 1)
            self.summary_labels[name] = value
        self.summary_grid.setColumnStretch(1, 1)
        self.summary_grid.setColumnStretch(3, 1)
        summary_layout.addWidget(details)
        root.addWidget(self.summary_frame)

        results_panel = QFrame()
        results_panel.setObjectName("subnetResultsPanel")
        results_layout = QVBoxLayout(results_panel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)
        result_heading = QHBoxLayout()
        result_heading.setContentsMargins(14, 11, 14, 10)
        result_title = QLabel("划分结果")
        result_title.setObjectName("subnetSectionTitle")
        self.loaded_label = QLabel("尚未生成结果")
        self.loaded_label.setObjectName("subnetResultBadge")
        self.copy_button = QPushButton("复制选中")
        self.copy_button.setObjectName("secondary")
        self.export_button = QPushButton("导出已加载")
        self.export_button.setObjectName("secondary")
        result_heading.addWidget(result_title)
        result_heading.addSpacing(6)
        result_heading.addWidget(self.loaded_label)
        result_heading.addStretch()
        results_layout.addLayout(result_heading)

        navigation = QHBoxLayout()
        navigation.setContentsMargins(14, 0, 14, 10)
        navigation.setSpacing(8)
        self.locate_ip = QLineEdit()
        self.locate_ip.setPlaceholderText("输入 IP，定位它所属的等长子网")
        self.locate_button = QPushButton("定位子网")
        self.locate_button.setObjectName("secondary")
        self.reset_window_button = QPushButton("回到开头")
        self.reset_window_button.setObjectName("neutral")
        navigation.addWidget(self.locate_ip, 1)
        navigation.addWidget(self.locate_button)
        navigation.addWidget(self.reset_window_button)
        navigation.addStretch()
        toolbar_divider = QFrame()
        toolbar_divider.setObjectName("subnetToolbarDivider")
        toolbar_divider.setFrameShape(QFrame.VLine)
        navigation.addWidget(toolbar_divider)
        navigation.addSpacing(3)
        navigation.addWidget(self.copy_button)
        navigation.addWidget(self.export_button)
        results_layout.addLayout(navigation)

        self.table = QTableView()
        self.table.setObjectName("subnetResultTable")
        self.table.setMinimumHeight(420)
        self.table.setModel(self.model)
        configure_table(self.table)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(64)
        self.table.viewport().installEventFilter(self)
        results_layout.addWidget(self.table, 1)
        self.status = QLabel("输入基础网络并选择划分方式")
        self.status.setObjectName("subnetStatus")
        results_layout.addWidget(self.status)
        root.addWidget(results_panel)

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.flsm_basis.currentIndexChanged.connect(self._basis_changed)
        self.calculate_button.clicked.connect(self.calculate)
        self.reset_button.clicked.connect(self.reset)
        self.locate_button.clicked.connect(self.locate)
        self.reset_window_button.clicked.connect(self.return_to_start)
        self.copy_button.clicked.connect(self.copy_selected)
        self.export_button.clicked.connect(self.export_loaded_results)
        self.model.load_state_changed.connect(self._update_navigation)
        self._mode_changed()
        self._basis_changed()
        self._update_navigation()
        # Establish cross-platform minimums synchronously.  Windows may not
        # deliver the zero-delay resize timer before the first event flush.
        self._resize_result_columns()
        self.schedule_result_column_resize()

    def showEvent(self, event):
        super().showEvent(event)
        self.schedule_result_column_resize()

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
            if self.mode.currentData() == "flsm":
                raw_value = self.flsm_value.text().strip().lstrip("/")
                if not raw_value:
                    raise ValueError("请输入目标前缀或子网数量")
                try:
                    value = int(raw_value)
                except ValueError as exc:
                    raise ValueError("目标前缀或子网数量必须是整数") from exc
                if self.flsm_basis.currentData() == "prefix":
                    plan = FLSMPlan(network, value)
                else:
                    plan = flsm_by_count(network, value)
                _first, _last, usable = usable_range(plan.subnet_at(0))
                self._show_summary(network)
                self.model.set_flsm(plan)
                self._show_plan_metrics(
                    "FLSM", plan.total, f"/{plan.target_prefix}", f"{usable:,} / 子网"
                )
                self.status.setText(
                    f"已将 {network.with_prefixlen} 划分为 {plan.total:,} 个 /{plan.target_prefix} 子网"
                )
            else:
                requirements = parse_host_requirements(self.vlsm_requirements.text())
                allocations = allocate_vlsm(network, requirements)
                prefixes = [allocation.network.prefixlen for allocation in allocations]
                prefix_text = (
                    f"/{prefixes[0]}" if len(set(prefixes)) == 1
                    else f"/{min(prefixes)} – /{max(prefixes)}"
                )
                self._show_summary(network)
                self.model.set_vlsm(allocations)
                self._show_plan_metrics(
                    "VLSM", len(allocations), prefix_text, f"{sum(requirements):,} 个需求地址"
                )
                self.status.setText(f"已完成 {len(allocations)} 个 VLSM 子网分配")
            self._update_navigation()
            self.schedule_result_column_resize()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "输入有误", str(exc))

    def _show_summary(self, network):
        summary = network_summary(network)
        self.summary_network.setText(
            f"{summary['IP 版本']} · {summary['规范网络']} · {summary['地址属性']}"
        )
        for name, label in self.summary_labels.items():
            value = summary[name]
            label.setText(f"{value:,}" if isinstance(value, int) else str(value))

    def _show_plan_metrics(self, mode, count, prefix, capacity):
        values = {
            "规划模式": mode,
            "子网数量": f"{count:,}",
            "前缀规划": prefix,
            "可用容量": capacity,
        }
        for name, value in values.items():
            self.metric_values[name].setText(value)

    def reset(self):
        self.base_network.setText("192.168.1.0/24")
        self.mode.setCurrentIndex(0)
        self.flsm_basis.setCurrentIndex(0)
        self.flsm_value.setText("28")
        self.vlsm_requirements.setText("120, 60, 30, 10")
        self.locate_ip.clear()
        for label in self.summary_labels.values():
            label.setText("—")
        self.summary_network.setText("等待计算")
        for label in self.metric_values.values():
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
        self.reset_window_button.setEnabled(
            bool(self.model.plan and self.model.window_start > 0)
        )
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
