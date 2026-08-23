import asyncio
import contextlib
import ipaddress
import threading
from pathlib import Path
from typing import List

from fuzztoolbox.ui.style_loader import apply_style, theme_color

try:
    from PySide6.QtCore import (
        QAbstractTableModel,
        QEvent,
        QModelIndex,
        QObject,
        QSettings,
        QSortFilterProxyModel,
        Qt,
        QThread,
        QTimer,
        Signal,
    )
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QComboBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSpinBox,
        QTableView,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少 GUI 依赖，请运行：pip install -e '.'") from exc

from ...core.network_info import NetworkInfo, get_network_info
from ...ui.components import configure_combo, configure_table
from .engine import ScanCancelled, Scanner
from .exporters import export_results
from .models import ScanConfig, ScanProgress, ScanResult
from .targets import parse_ports, parse_target

SCAN_SELECTOR_WIDTH = 180


class ResultModel(QAbstractTableModel):
    columns = ["IP 地址", "状态", "探测方式", "响应时间", "主机名", "开放端口"]

    def __init__(self):
        super().__init__()
        self.results: List[ScanResult] = []
        self._rows_by_ip = {}
        self.show_mac = True

    def rowCount(self, _parent=QModelIndex()):
        return len(self.results)

    def columnCount(self, _parent=QModelIndex()):
        return len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if section == 5:
                return "MAC 地址" if self.show_mac else "开放端口"
            return self.columns[section]
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        result = self.results[index.row()]
        if role == Qt.ToolTipRole and result.error:
            return result.error
        if role == Qt.ForegroundRole and index.column() == 1:
            return QColor("#67c23a" if result.is_alive else theme_color("text_muted"))
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        if role != Qt.DisplayRole:
            return None
        values = [
            result.ip,
            "在线" if result.is_alive else "离线",
            result.method.upper(),
            f"{result.response_time_ms:.2f} ms" if result.response_time_ms is not None else "—",
            result.hostname or ("解析中…" if result.details_pending else "—"),
            (result.mac or ("解析中…" if result.details_pending else "—"))
            if self.show_mac
            else (", ".join(map(str, result.open_ports)) or "—"),
        ]
        return values[index.column()]

    def clear(self):
        self.beginResetModel()
        self.results.clear()
        self._rows_by_ip.clear()
        self.endResetModel()

    def add_batch(self, batch: List[ScanResult]):
        if not batch:
            return
        new_results = []
        for result in batch:
            row = self._rows_by_ip.get(result.ip)
            if row is None:
                new_results.append(result)
                continue
            self.results[row] = result
            self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))
        if new_results:
            first = len(self.results)
            self.beginInsertRows(QModelIndex(), first, first + len(new_results) - 1)
            for result in new_results:
                self._rows_by_ip[result.ip] = len(self.results)
                self.results.append(result)
            self.endInsertRows()

    def set_scan_method(self, method: str):
        self.show_mac = method == "ping"
        self.headerDataChanged.emit(Qt.Horizontal, 5, 5)


class ResultFilterModel(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.query = ""
        self.status = "all"
        self.setDynamicSortFilter(True)

    def set_query(self, query: str):
        self.query = query.strip().lower()
        self.invalidateFilter()

    def set_status(self, status: str):
        self.status = status
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        result = self.sourceModel().results[source_row]
        if self.status == "online" and not result.is_alive:
            return False
        if self.status == "offline" and result.is_alive:
            return False
        if not self.query:
            return True
        try:
            ipaddress.IPv4Address(self.query)
            return result.ip == self.query
        except ipaddress.AddressValueError:
            pass
        searchable = " ".join(
            [
                result.ip,
                result.hostname or "",
                result.mac or "",
                ",".join(map(str, result.open_ports)),
            ]
        ).lower()
        return self.query in searchable


class WorkerSignals(QObject):
    results = Signal(list)
    updates = Signal(list)
    progress = Signal(object)
    completed = Signal(bool, str)


class ScanWorker(QThread):
    def __init__(self, target_text: str, config: ScanConfig, network_info: NetworkInfo):
        super().__init__()
        self.target_text = target_text
        self.config = config
        self.network_info = network_info
        self.signals = WorkerSignals()
        self.scanner = None
        self.loop = None
        self.scan_task = None
        self._cancel_requested = threading.Event()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.scanner = Scanner(self.config, self.network_info)
        success = False
        message = "扫描已停止"
        try:
            target = parse_target(self.target_text)
            self.scan_task = self.loop.create_task(
                self.scanner.scan(
                    target,
                    self.signals.results.emit,
                    self.signals.progress.emit,
                    on_updates=self.signals.updates.emit,
                    batch_size=512,
                    retain_results=False,
                )
            )
            if self._cancel_requested.is_set():
                self.scanner.cancel()
            self.loop.run_until_complete(self.scan_task)
            success, message = True, "扫描完成"
        except (ScanCancelled, asyncio.CancelledError):
            success, message = False, "扫描已停止"
        except Exception as exc:
            success, message = False, f"扫描失败：{exc}"
        finally:
            with contextlib.suppress(Exception):
                self.loop.run_until_complete(
                    asyncio.wait_for(self.loop.shutdown_asyncgens(), timeout=0.5)
                )
            self.loop.close()
        self.signals.completed.emit(success, message)

    def cancel(self, force=False):
        self._cancel_requested.set()
        if self.loop and self.scanner:
            def cancel_in_loop():
                self.scanner.cancel()
                if force and self.scan_task and not self.scan_task.done():
                    self.scan_task.cancel()

            with contextlib.suppress(RuntimeError):
                self.loop.call_soon_threadsafe(cancel_in_loop)


class IPScannerPage(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("1024_byteeeee", "FuzzToolBox")
        self.worker = None
        self.model = ResultModel()
        self.proxy_model = ResultFilterModel()
        self.proxy_model.setSourceModel(self.model)
        self._auto_scroll = False
        self._accept_updates = False
        self._scroll_pending = False
        self._column_resize_pending = False
        self._stop_watchdog = QTimer(self)
        self._stop_watchdog.setSingleShot(True)
        self._stop_watchdog.timeout.connect(self._force_stop_scan)
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(12)

        self.network_info = get_network_info()
        default_start, default_end = self.network_info.scan_range or ("", "")
        default_cidr = self.network_info.cidr or ""
        self.network_label = QLabel(f"本机网络  {self.network_info.display_text()}")
        self.network_label.setObjectName("networkInfo")
        apply_style(self.network_label, "tools.ip_scanner.page:259")
        self.network_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.network_label)

        range_controls = QHBoxLayout()
        range_label = QLabel("扫描范围")
        apply_style(range_label, "tools.ip_scanner.page:268")
        self.range_mode = QComboBox()
        self.range_mode.addItem("起始 IP - 结束 IP", "range")
        self.range_mode.addItem("CIDR / 单 IP", "cidr")
        configure_combo(self.range_mode)
        self.range_mode.setFixedWidth(SCAN_SELECTOR_WIDTH)
        self.target = QLineEdit(default_cidr)
        self.target.setPlaceholderText("例如：192.168.1.0/24 或 192.168.1.10")
        self.start_ip = QLineEdit(default_start)
        self.start_ip.setPlaceholderText("起始 IP，例如 192.168.1.1")
        self.end_ip = QLineEdit(default_end)
        self.end_ip.setPlaceholderText("结束 IP，例如 192.168.1.254")
        self.range_separator = QLabel("至")
        range_controls.addWidget(range_label)
        range_controls.addWidget(self.range_mode)
        range_controls.addWidget(self.target, 1)
        range_controls.addWidget(self.start_ip, 1)
        range_controls.addWidget(self.range_separator)
        range_controls.addWidget(self.end_ip, 1)
        layout.addLayout(range_controls)

        controls = QHBoxLayout()
        method_label = QLabel("扫描方式")
        apply_style(method_label, "tools.ip_scanner.page:291")
        self.method = QComboBox()
        self.method.addItem("系统 Ping", "ping")
        self.method.addItem("TCP 端口探测", "tcp")
        configure_combo(self.method)
        self.method.setFixedWidth(SCAN_SELECTOR_WIDTH)
        ports_label = QLabel("探测端口")
        apply_style(ports_label, "tools.ip_scanner.page:298")
        self.ports = QLineEdit("22,80,443,445,3389,8080")
        self.ports.setMinimumWidth(210)
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 512)
        self.concurrency.setValue(64)
        self.concurrency.setPrefix("并发 ")
        self.concurrency.setMinimumWidth(115)
        self.start_button = QPushButton("开始扫描")
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("danger")
        self.stop_button.setEnabled(False)
        self.export_button = QPushButton("导出")
        self.export_button.setObjectName("secondary")
        for widget in (
            method_label,
            self.method,
            ports_label,
            self.ports,
            self.concurrency,
            self.start_button,
            self.stop_button,
            self.export_button,
        ):
            controls.addWidget(widget)
        controls.insertStretch(5, 1)
        layout.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.status_label = QLabel("就绪")
        apply_style(self.status_label, "tools.ip_scanner.page:330")
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)

        filter_controls = QHBoxLayout()
        search_label = QLabel("搜索结果")
        apply_style(search_label, "tools.ip_scanner.page:336")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入精确 IP，或搜索主机名、MAC 地址、端口")
        self.status_filter = QComboBox()
        self.status_filter.addItem("全部结果", "all")
        self.status_filter.addItem("仅在线", "online")
        self.status_filter.addItem("仅离线", "offline")
        self.status_filter.setMinimumWidth(125)
        configure_combo(self.status_filter)
        filter_controls.addWidget(search_label)
        filter_controls.addWidget(self.search_input, 1)
        filter_controls.addWidget(self.status_filter)
        layout.addLayout(filter_controls)

        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        configure_table(self.table)
        self.table.setSortingEnabled(False)
        self.table.viewport().installEventFilter(self)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(65)
        layout.addWidget(self.table, 1)
        self.schedule_result_column_resize()

        self.start_button.clicked.connect(self.start_scan)
        self.stop_button.clicked.connect(self.stop_scan)
        self.export_button.clicked.connect(self.export)
        self.range_mode.currentIndexChanged.connect(self.update_range_mode)
        self.method.currentIndexChanged.connect(self._update_method_controls)
        self.search_input.textChanged.connect(self.proxy_model.set_query)
        self.status_filter.currentIndexChanged.connect(
            lambda: self.proxy_model.set_status(self.status_filter.currentData())
        )
        self.model.rowsInserted.connect(self._scroll_to_latest)
        self.update_range_mode()
        self._update_method_controls()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule_result_column_resize()

    def showEvent(self, event):
        super().showEvent(event)
        self.schedule_result_column_resize()

    def eventFilter(self, watched, event):
        if watched is self.table.viewport() and event.type() in (QEvent.Resize, QEvent.Show):
            self.schedule_result_column_resize()
        return super().eventFilter(watched, event)

    def schedule_result_column_resize(self):
        if self._column_resize_pending:
            return
        self._column_resize_pending = True
        QTimer.singleShot(0, self._apply_scheduled_column_resize)

    def _apply_scheduled_column_resize(self):
        self._column_resize_pending = False
        self._resize_result_columns()

    def _resize_result_columns(self):
        if not hasattr(self, "table"):
            return
        available = self.table.viewport().width()
        weights = (18, 12, 14, 14, 21, 21)
        widths = [max(65, available * weight // sum(weights)) for weight in weights]
        widths[-1] += available - sum(widths)
        for column, width in enumerate(widths):
            self.table.horizontalHeader().resizeSection(column, max(65, width))

    def _load_settings(self):
        self.range_mode.setCurrentIndex(
            max(0, self.range_mode.findData(self.settings.value("scan/range_mode", "range")))
        )
        self.method.setCurrentIndex(
            max(0, self.method.findData(self.settings.value("scan/method", "ping")))
        )
        try:
            saved_concurrency = int(self.settings.value("scan/concurrency", 64))
        except (TypeError, ValueError):
            saved_concurrency = 64
        self.concurrency.setValue(saved_concurrency)
        self.ports.setText(str(self.settings.value("scan/ports", self.ports.text())))
        self.update_range_mode()
        self._update_method_controls()
        self.schedule_result_column_resize()

    def _save_settings(self):
        self.settings.setValue("scan/range_mode", self.range_mode.currentData())
        self.settings.setValue("scan/method", self.method.currentData())
        self.settings.setValue("scan/concurrency", self.concurrency.value())
        self.settings.setValue("scan/ports", self.ports.text())

    def start_scan(self):
        if self.worker and self.worker.isRunning():
            return
        self._refresh_network_info()
        try:
            target_text = self._target_text()
            target = parse_target(target_text)
            ports = parse_ports(self.ports.text())
            config = ScanConfig(
                method=self.method.currentData(),
                ports=ports,
                concurrency=self.concurrency.value(),
                # Two short two-packet bursts balance cold-start reliability and speed.
                retries=1 if self.method.currentData() == "ping" else 0,
                include_dead=True,
                resolve_hostname=True,
            )
            config.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "输入有误", str(exc))
            return
        self.model.clear()
        self.model.set_scan_method(config.method)
        self.search_input.clear()
        self.status_filter.setCurrentIndex(0)
        self.progress.setValue(0)
        self._auto_scroll = True
        self._accept_updates = True
        self._set_running(True)

        worker = ScanWorker(target_text, config, self.network_info)
        self.worker = worker
        worker.signals.results.connect(
            lambda batch, active=worker: self.receive_results(active, batch)
        )
        worker.signals.updates.connect(
            lambda batch, active=worker: self.receive_results(active, batch)
        )
        worker.signals.progress.connect(
            lambda progress, active=worker: self.update_progress(active, progress)
        )
        worker.signals.completed.connect(
            lambda success, message, active=worker: self.scan_finished(
                active, success, message
            )
        )
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def stop_scan(self):
        worker = self.worker
        if worker and worker.isRunning():
            self._accept_updates = False
            self._auto_scroll = False
            self.status_label.setText("正在停止…")
            self.stop_button.setEnabled(False)
            # Stop feeding the GUI queue immediately. On very large/fast scans,
            # stale table/progress events can otherwise delay both the stop click
            # and the worker's completion notification for several seconds.
            with contextlib.suppress(RuntimeError):
                worker.signals.results.disconnect()
            with contextlib.suppress(RuntimeError):
                worker.signals.updates.disconnect()
            with contextlib.suppress(RuntimeError):
                worker.signals.progress.disconnect()
            worker.cancel()
            self._stop_watchdog.start(3000)

    def receive_results(self, worker, batch):
        if worker is self.worker and self._accept_updates:
            self.model.add_batch(batch)

    def update_progress(self, worker, progress: ScanProgress):
        if worker is not self.worker or not self._accept_updates:
            return
        value = int(progress.scanned / progress.total * 1000) if progress.total else 0
        self.progress.setValue(value)
        self.status_label.setText(
            f"已扫描 {progress.scanned:,} / {progress.total:,} · "
            f"在线 {progress.alive:,} · {progress.rate:,.0f} IP/s"
        )

    def scan_finished(self, worker, success: bool, message: str):
        if worker is not self.worker:
            return
        self._stop_watchdog.stop()
        self._accept_updates = False
        self._auto_scroll = False
        self._set_running(False)
        alive = sum(result.is_alive for result in self.model.results)
        offline = len(self.model.results) - alive
        self.status_label.setText(
            f"{message} · 已扫描 {len(self.model.results)} 个地址 · "
            f"在线 {alive} 台 · 离线 {offline} 台"
        )
        if not success and "停止" not in message:
            QMessageBox.warning(self, "扫描错误", message)
        self.worker = None

    def _force_stop_scan(self):
        worker = self.worker
        if not worker or not worker.isRunning():
            return
        worker.cancel(force=True)
        self.status_label.setText("正在强制结束剩余系统探测…")
        self._stop_watchdog.start(2000)

    def _set_running(self, running: bool):
        self.stop_button.setEnabled(running)
        for widget in (
            self.range_mode,
            self.target,
            self.start_ip,
            self.end_ip,
            self.method,
            self.ports,
            self.concurrency,
            self.start_button,
            self.export_button,
            self.search_input,
            self.status_filter,
        ):
            widget.setEnabled(not running)
        if not running:
            self.update_range_mode()
            self._update_method_controls()

    def update_range_mode(self):
        is_range = self.range_mode.currentData() == "range"
        self.target.setVisible(not is_range)
        self.start_ip.setVisible(is_range)
        self.range_separator.setVisible(is_range)
        self.end_ip.setVisible(is_range)

    def _update_method_controls(self):
        self.ports.setEnabled(self.method.isEnabled() and self.method.currentData() == "tcp")

    def _refresh_network_info(self):
        previous = self.network_info
        latest = get_network_info(include_gateway=False)
        if not latest.ip:
            return
        old_range = previous.scan_range or ("", "")
        old_cidr = previous.cidr or ""
        range_uses_default = (self.start_ip.text(), self.end_ip.text()) == old_range
        cidr_uses_default = self.target.text() == old_cidr
        if latest.ip == previous.ip and latest.interface == previous.interface:
            latest = NetworkInfo(
                interface=latest.interface,
                ip=latest.ip,
                prefix_length=latest.prefix_length,
                gateway=previous.gateway,
                mac=latest.mac,
            )
        self.network_info = latest
        self.network_label.setText(f"本机网络  {latest.display_text()}")
        if range_uses_default and latest.scan_range:
            self.start_ip.setText(latest.scan_range[0])
            self.end_ip.setText(latest.scan_range[1])
        if cidr_uses_default and latest.cidr:
            self.target.setText(latest.cidr)

    def _target_text(self) -> str:
        if self.range_mode.currentData() == "range":
            start = self.start_ip.text().strip()
            end = self.end_ip.text().strip()
            if not start or not end:
                raise ValueError("请输入完整的起始 IP 和结束 IP")
            return f"{start}-{end}"
        return self.target.text().strip()

    def _scroll_to_latest(self, *_args):
        if not self._auto_scroll or self._scroll_pending:
            return
        self._scroll_pending = True
        QTimer.singleShot(80, self._perform_auto_scroll)

    def _perform_auto_scroll(self):
        self._scroll_pending = False
        if self._auto_scroll:
            self.table.scrollToBottom()

    def export(self):
        if not self.model.results:
            QMessageBox.information(self, "暂无结果", "当前没有可导出的扫描结果。")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出扫描结果",
            "fuzztoolbox-ip-scanner-results.csv",
            "CSV (*.csv);;JSON (*.json)",
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".json" if "JSON" in selected_filter else ".csv"
        try:
            export_results(Path(path), self.model.results)
            self.status_label.setText(f"已导出到 {path}")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def prepare_close(self, on_ready) -> bool:
        self._stop_watchdog.stop()
        self._save_settings()
        worker = self.worker
        if worker and worker.isRunning():
            worker.cancel()
            if not worker.wait(3000):
                self.status_label.setText("正在停止扫描，完成后将自动关闭…")
                worker.finished.connect(on_ready)
                return False
        return True
