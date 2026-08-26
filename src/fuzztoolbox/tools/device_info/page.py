from PySide6.QtCore import Qt, QThread, QTime, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...ui.components import SkeletonBar
from ...ui.style_loader import apply_style
from ...ui.tool_runtime import ToolActivity
from .collector import DeviceReport, InfoSection, collect_device_info

# 设备信息实时刷新间隔。
AUTO_REFRESH_INTERVAL_MS = 2000


class DeviceInfoWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.completed.emit(collect_device_info())
        # This is the worker boundary: platform probes may raise ctypes, psutil,
        # subprocess or decoding errors, all of which must become a UI failure signal.
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


def collect_screen_section() -> InfoSection:
    rows = []
    screens = QGuiApplication.screens()
    primary = QGuiApplication.primaryScreen()
    for index, screen in enumerate(screens, start=1):
        geometry = screen.geometry()
        ratio = float(screen.devicePixelRatio())
        logical = f"{geometry.width()} × {geometry.height()}"
        physical = f"{round(geometry.width() * ratio)} × {round(geometry.height() * ratio)}"
        name = screen.name() or f"显示器 {index}"
        model_parts = [value for value in (screen.manufacturer(), screen.model()) if value]
        prefix = f"显示器 {index}{'（主屏幕）' if screen is primary else ''}"
        details = [
            name,
            " / ".join(model_parts) if model_parts else "型号未提供",
            f"逻辑 {logical}",
            f"实际像素 {physical}",
            f"像素比 {ratio:g}（{ratio * 100:.0f}%）",
            f"{screen.refreshRate():.2f} Hz",
            f"{screen.depth()} 位色深",
            f"逻辑 DPI {screen.logicalDotsPerInch():.1f}",
            f"物理 DPI {screen.physicalDotsPerInch():.1f}",
            f"{screen.physicalSize().width():.0f} × {screen.physicalSize().height():.0f} mm",
        ]
        rows.append((prefix, " · ".join(details)))
    return InfoSection("显示器", tuple(rows) or (("显示器", "未检测到"),))


class DeviceInfoPage(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.report = None
        self._structure = None
        self._value_labels = []
        self._build_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(AUTO_REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._auto_refresh)

    def _build_ui(self):
        self.setObjectName("deviceInfoWorkspace")
        apply_style(self, "tools.device_info.page:workspace")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("deviceInfoScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("deviceInfoContent")
        self.root = QVBoxLayout(content)
        self.root.setContentsMargins(20, 18, 20, 14)
        self.root.setSpacing(12)
        self.root.setSizeConstraint(QLayout.SetMinimumSize)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll)

        heading = QHBoxLayout()
        intro = QLabel("查看当前设备的系统、硬件、屏幕、存储与网络信息，数据实时更新")
        intro.setObjectName("deviceInfoIntro")
        self.copy_button = QPushButton("复制全部")
        self.copy_button.setObjectName("secondary")
        self.refresh_button = QPushButton("刷新信息")
        heading.addWidget(intro)
        heading.addStretch()
        heading.addWidget(self.copy_button)
        heading.addWidget(self.refresh_button)
        self.root.addLayout(heading)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        self.root.addWidget(self.progress)
        self.status = QLabel("打开工具后将实时更新设备信息")
        self.status.setObjectName("deviceInfoStatus")
        self.root.addWidget(self.status)
        self.sections_host = QWidget()
        self.sections_layout = QVBoxLayout(self.sections_host)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(12)
        self.root.addWidget(self.sections_host)
        self.root.addStretch()

        self.refresh_button.clicked.connect(self.refresh)
        self.copy_button.clicked.connect(self.copy_all)
        self.copy_button.setEnabled(False)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_timer.start()
        if self.report is None:
            self.refresh()

    def hideEvent(self, event):
        self._refresh_timer.stop()
        super().hideEvent(event)

    def refresh(self):
        self._start_refresh(manual=True)

    def _auto_refresh(self):
        self._start_refresh(manual=False)

    def _start_refresh(self, manual: bool):
        if self.worker and self.worker.isRunning():
            return
        if self.report is None:
            # 首次加载还没有任何数据，用骨架屏卡片占位表示正在读取。
            self._show_skeleton()
        if manual:
            self.progress.setVisible(True)
            self.refresh_button.setEnabled(False)
            self.copy_button.setEnabled(False)
            self.status.setText("正在读取设备信息…")
        worker = DeviceInfoWorker(self)
        self.worker = worker
        worker.completed.connect(self._loaded)
        worker.failed.connect(self._failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _clear_sections(self):
        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._value_labels = []
        self._structure = None

    def _show_skeleton(self):
        self._clear_sections()
        # 骨架分区数量、行数与行高贴近真实报告结构，减少加载完成后的尺寸跳变。
        # 长文本行（系统版本、显示器详情）用更高的占位条近似其换行后的高度。
        skeleton_structure = (
            [17, 17, 17, 17, 80, 17, 19],  # 设备概览（系统版本为长文本）
            [17] * 6,                        # 处理器
            [17],                            # 图形处理器
            [17] * 4,                        # 内存
            [17] * 4,                        # 磁盘
            [17] * 3,                        # 网络
            [17, 19],                        # 电池
            [111],                           # 显示器（长文本详情）
        )
        for row_heights in skeleton_structure:
            self._add_skeleton_panel(row_heights)

    def _add_skeleton_panel(self, row_heights):
        panel = QFrame()
        panel.setObjectName("deviceInfoSection")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 13, 16, 15)
        layout.setSpacing(9)
        # 标题 25px，与真实分区标题一致。
        layout.addWidget(SkeletonBar(height=25, width_ratio=0.24))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for row, height in enumerate(row_heights):
            key = SkeletonBar(height=height)
            key.setFixedWidth(96)
            grid.addWidget(key, row, 0)
            grid.addWidget(SkeletonBar(height=height, width_ratio=0.62), row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.sections_layout.addWidget(panel)

    def _loaded(self, report: DeviceReport):
        screen_section = collect_screen_section()
        self.report = DeviceReport(report.sections + (screen_section,))
        self._render(self.report)
        self.progress.setVisible(False)
        self.refresh_button.setEnabled(True)
        self.copy_button.setEnabled(True)
        updated_at = QTime.currentTime().toString("HH:mm:ss")
        self.status.setText(f"实时更新中 · 最近刷新 {updated_at}")
        self.worker = None

    def _failed(self, message: str):
        self.progress.setVisible(False)
        self.refresh_button.setEnabled(True)
        self.copy_button.setEnabled(self.report is not None)
        self.status.setText(f"读取失败：{message}")
        self.worker = None

    @staticmethod
    def _structure_signature(report: DeviceReport):
        return tuple(
            (section.title, tuple(name for name, _ in section.rows))
            for section in report.sections
        )

    def _render(self, report: DeviceReport):
        signature = self._structure_signature(report)
        if signature == self._structure and self._value_labels:
            # 结构未变化时只更新数值，避免重建卡片造成界面闪烁。
            index = 0
            for section in report.sections:
                for _, value in section.rows:
                    self._value_labels[index].setText(value)
                    index += 1
            return
        self._clear_sections()
        for section in report.sections:
            panel = QFrame()
            panel.setObjectName("deviceInfoSection")
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(16, 13, 16, 15)
            layout.setSpacing(9)
            title = QLabel(section.title)
            title.setObjectName("deviceInfoSectionTitle")
            layout.addWidget(title)
            grid = QGridLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(8)
            for row, (name, value) in enumerate(section.rows):
                key = QLabel(name)
                key.setObjectName("deviceInfoKey")
                val = QLabel(value)
                val.setObjectName("deviceInfoValue")
                val.setWordWrap(True)
                val.setTextInteractionFlags(Qt.TextSelectableByMouse)
                grid.addWidget(key, row, 0, Qt.AlignTop)
                grid.addWidget(val, row, 1)
                self._value_labels.append(val)
            grid.setColumnStretch(1, 1)
            layout.addLayout(grid)
            self.sections_layout.addWidget(panel)
        self._structure = signature

    def prepare_close(self, on_ready) -> bool:
        self._refresh_timer.stop()
        worker = self.worker
        if worker and worker.isRunning() and not worker.wait(3000):
            worker.finished.connect(on_ready)
            return False
        return True

    def runtime_activity(self) -> ToolActivity:
        if self.worker and self.worker.isRunning():
            return ToolActivity.running("正在读取设备信息")
        if self._refresh_timer.isActive():
            return ToolActivity.running("正在实时更新设备信息")
        return ToolActivity()

    def copy_all(self):
        if not self.report:
            return
        QGuiApplication.clipboard().setText(self.report.text())
        self.status.setText("已复制全部设备信息")
