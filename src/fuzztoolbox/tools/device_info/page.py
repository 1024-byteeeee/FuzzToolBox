from PySide6.QtCore import Qt, QThread, QTimer, QTime, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QProgressBar,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .collector import DeviceReport, InfoSection, collect_device_info
from ...ui.style_loader import apply_style

# 设备信息实时刷新间隔。
AUTO_REFRESH_INTERVAL_MS = 2000


class DeviceInfoWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.completed.emit(collect_device_info())
        except Exception as exc:  # Keep a platform-specific probe failure inside the tool page.
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
        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._value_labels = []
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
        if worker and worker.isRunning():
            if not worker.wait(3000):
                worker.finished.connect(on_ready)
                return False
        return True

    def copy_all(self):
        if not self.report:
            return
        QGuiApplication.clipboard().setText(self.report.text())
        self.status.setText("已复制全部设备信息")
