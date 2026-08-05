import asyncio
import contextlib
import ipaddress
import sys
import threading
from pathlib import Path
from typing import List

try:
    from PySide6.QtCore import (
        QAbstractTableModel,
        QModelIndex,
        QObject,
        QSortFilterProxyModel,
        Qt,
        QThread,
        QTimer,
        Signal,
    )
    from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPalette
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListView,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSpinBox,
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QTableView,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise SystemExit("缺少 GUI 依赖，请运行：pip install -e '.[gui]'") from exc

from . import __version__
from .engine import ScanCancelled, Scanner
from .exporters import export_results
from .models import ScanConfig, ScanProgress, ScanResult
from .network_info import NetworkInfo, get_network_info
from .targets import parse_ports, parse_target


ASSET_DIR = Path(__file__).resolve().parent / "assets"

STYLE = """
QWidget { background: #f5f7fa; color: #303133; font-size: 13px; }
QMainWindow { background: #f5f7fa; }
QLineEdit, QComboBox, QSpinBox {
  background: white; border: 1px solid #dcdfe6; border-radius: 6px; padding: 7px 10px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #409eff; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
  background: #f0f2f5; color: #909399; border-color: #e4e7ed;
}
QComboBox { padding-right: 34px; }
QComboBox::drop-down {
  subcontrol-origin: padding; subcontrol-position: top right; width: 28px;
  border: 0; background: transparent;
}
QComboBox::drop-down:hover { background: #f0f2f5; }
QComboBox::down-arrow { image: url(%CHEVRON_DOWN%); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: white; border: 0; padding: 4px; outline: 0; }
QSpinBox { padding-right: 28px; }
QSpinBox::up-button, QSpinBox::down-button {
  subcontrol-origin: border; width: 25px; background: transparent; border: 0;
}
QSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 6px; }
QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 6px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #f0f2f5; }
QSpinBox::up-arrow { image: url(%CHEVRON_UP%); width: 10px; height: 10px; }
QSpinBox::down-arrow { image: url(%CHEVRON_SMALL_DOWN%); width: 10px; height: 10px; }
QPushButton {
  background: #409eff; color: white; border: 0; border-radius: 6px; padding: 8px 16px;
}
QPushButton:hover { background: #66b1ff; }
QPushButton:disabled { background: #c0c4cc; color: #f5f7fa; }
QPushButton#secondary { background: white; color: #606266; border: 1px solid #dcdfe6; }
QPushButton#danger { background: #f56c6c; }
QTableView {
  background: white; alternate-background-color: #fafcff; border: 1px solid #ebeef5;
  border-radius: 8px; gridline-color: #e4e7ed; selection-background-color: #ecf5ff;
}
QTableView::item { border-right: 1px solid #e4e7ed; border-bottom: 1px solid #e4e7ed; }
QTableView::item:selected { background: #ecf5ff; }
QHeaderView::section {
  background: #fafafa; padding: 9px; border: 0; border-bottom: 1px solid #ebeef5;
}
QScrollBar:vertical { background: #f5f7fa; width: 10px; margin: 2px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #c0c4cc; min-height: 28px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: #909399; }
QScrollBar:horizontal { background: #f5f7fa; height: 10px; margin: 2px; border-radius: 5px; }
QScrollBar::handle:horizontal { background: #c0c4cc; min-width: 28px; border-radius: 4px; }
QScrollBar::handle:horizontal:hover { background: #909399; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; background: none; border: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QProgressBar { background: #e4e7ed; border: 0; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #409eff; border-radius: 4px; }
""".replace("%CHEVRON_DOWN%", (ASSET_DIR / "chevron-down.svg").as_posix()).replace(
    "%CHEVRON_UP%", (ASSET_DIR / "chevron-up.svg").as_posix()
).replace("%CHEVRON_SMALL_DOWN%", (ASSET_DIR / "chevron-small-down.svg").as_posix())


class ComboItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(34)
        return size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        rect = option.rect.adjusted(4, 2, -4, -2)
        if option.state & (QStyle.State_MouseOver | QStyle.State_Selected):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ecf5ff"))
            painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor("#303133"))
        painter.drawText(rect.adjusted(10, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, str(index.data()))
        painter.restore()


def configure_combo(combo: QComboBox) -> None:
    view = QListView(combo)
    view.setMouseTracking(True)
    view.setSpacing(0)
    view.setItemDelegate(ComboItemDelegate(view))
    combo.setView(view)


class GridCellDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        styled_option = QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)
        foreground = index.data(Qt.ForegroundRole)
        text_color = (
            foreground
            if isinstance(foreground, QColor)
            else styled_option.palette.color(QPalette.Text)
        )
        styled_option.palette.setColor(QPalette.HighlightedText, text_color)
        super().paint(painter, styled_option, index)
        painter.save()
        painter.setPen(QColor("#e4e7ed"))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.drawLine(option.rect.topRight(), option.rect.bottomRight())
        painter.restore()


class ResultModel(QAbstractTableModel):
    columns = ["IP 地址", "状态", "探测方式", "响应时间", "主机名", "开放端口"]

    def __init__(self):
        super().__init__()
        self.results: List[ScanResult] = []
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
            return QColor("#67c23a" if result.is_alive else "#909399")
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        if role != Qt.DisplayRole:
            return None
        values = [
            result.ip,
            "在线" if result.is_alive else "离线",
            result.method.upper(),
            f"{result.response_time_ms:.2f} ms" if result.response_time_ms is not None else "—",
            result.hostname or "—",
            (result.mac or "—")
            if self.show_mac
            else (", ".join(map(str, result.open_ports)) or "—"),
        ]
        return values[index.column()]

    def clear(self):
        self.beginResetModel()
        self.results.clear()
        self.endResetModel()

    def add_batch(self, batch: List[ScanResult]):
        if not batch:
            return
        first = len(self.results)
        self.beginInsertRows(QModelIndex(), first, first + len(batch) - 1)
        self.results.extend(batch)
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
                    retain_results=False,
                )
            )
            if self._cancel_requested.is_set():
                self.scanner.cancel()
                self.scan_task.cancel()
            self.loop.run_until_complete(self.scan_task)
            success, message = True, "扫描完成"
        except (ScanCancelled, asyncio.CancelledError):
            success, message = False, "扫描已停止"
        except Exception as exc:
            success, message = False, f"扫描失败：{exc}"
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.run_until_complete(asyncio.sleep(0))
            self.loop.close()
        self.signals.completed.emit(success, message)

    def cancel(self):
        self._cancel_requested.set()
        if self.loop and self.scanner:
            def cancel_in_loop():
                self.scanner.cancel()
                if self.scan_task and not self.scan_task.done():
                    self.scan_task.cancel()

            with contextlib.suppress(RuntimeError):
                self.loop.call_soon_threadsafe(cancel_in_loop)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(str(ASSET_DIR / "app-icon.png")))
        self.worker = None
        self.setWindowTitle(f"IP-Scanner v{__version__}")
        self.resize(1180, 760)
        self.model = ResultModel()
        self.proxy_model = ResultFilterModel()
        self.proxy_model.setSourceModel(self.model)
        self._auto_scroll = False
        self._accept_updates = False
        self._stop_watchdog = QTimer(self)
        self._stop_watchdog.setSingleShot(True)
        self._stop_watchdog.timeout.connect(self._force_stop_scan)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(12)

        title = QLabel("IP-Scanner")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #303133;")
        subtitle = QLabel("快速发现局域网中的在线设备")
        subtitle.setStyleSheet("color: #909399;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.network_info = get_network_info()
        default_start, default_end = self.network_info.scan_range or ("", "")
        default_cidr = self.network_info.cidr or ""
        self.network_label = QLabel(f"本机网络  {self.network_info.display_text()}")
        self.network_label.setObjectName("networkInfo")
        self.network_label.setStyleSheet(
            "QLabel#networkInfo { background: #ecf5ff; color: #406080; "
            "border: 1px solid #d9ecff; border-radius: 6px; padding: 8px 12px; }"
        )
        self.network_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.network_label)

        range_controls = QHBoxLayout()
        range_label = QLabel("扫描范围")
        range_label.setStyleSheet("font-weight: 600;")
        self.range_mode = QComboBox()
        self.range_mode.addItem("起始 IP - 结束 IP", "range")
        self.range_mode.addItem("CIDR / 单 IP", "cidr")
        configure_combo(self.range_mode)
        self.range_mode.setMinimumWidth(155)
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
        method_label.setStyleSheet("font-weight: 600;")
        self.method = QComboBox()
        self.method.addItem("系统 Ping", "ping")
        self.method.addItem("TCP 端口探测", "tcp")
        configure_combo(self.method)
        self.method.setMinimumWidth(165)
        ports_label = QLabel("探测端口")
        ports_label.setStyleSheet("font-weight: 600;")
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
        self.status_label.setStyleSheet("color: #606266;")
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)

        filter_controls = QHBoxLayout()
        search_label = QLabel("搜索结果")
        search_label.setStyleSheet("font-weight: 600;")
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
        self.table.setItemDelegate(GridCellDelegate(self.table))
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        layout.addWidget(self.table, 1)

        github_icon = (ASSET_DIR / "github.svg").as_posix()
        copyright_label = QLabel(
            f'IP-Scanner v{__version__} · © 2026 1024_byteeeee 版权所有 · '
            f'<img src="{github_icon}" width="14" height="14"> '
            '<a href="https://github.com/1024-byteeeee">GitHub</a>'
        )
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setStyleSheet("color: #909399; padding-top: 4px;")
        layout.addWidget(copyright_label)
        self.setCentralWidget(root)

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

        quit_action = QAction(self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

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
                retries=2 if self.method.currentData() == "ping" else 0,
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
        worker.cancel()
        self.status_label.setText("正在停止…正在等待当前系统探测退出")

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
        if self._auto_scroll:
            self.table.scrollToBottom()

    def export(self):
        if not self.model.results:
            QMessageBox.information(self, "暂无结果", "当前没有可导出的扫描结果。")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "导出扫描结果", "ip-scanner-results.csv", "CSV (*.csv);;JSON (*.json)"
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

    def closeEvent(self, event):
        self._stop_watchdog.stop()
        worker = self.worker
        if worker and worker.isRunning():
            worker.cancel()
            if not worker.wait(3000):
                self.status_label.setText("正在停止扫描，完成后将自动关闭…")
                worker.finished.connect(self.close)
                event.ignore()
                return
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("IP-Scanner")
    app.setApplicationVersion(__version__)
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
