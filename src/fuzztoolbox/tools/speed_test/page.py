"""PySide6 interface for the network speed test."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.style_loader import apply_style, set_style_state

from .engine import SpeedTestCancelled, SpeedTestEngine, SpeedTestResult


def format_speed(value: float) -> tuple[str, str]:
    if value >= 1000:
        return f"{value / 1000:.2f}", "Gbps"
    return f"{value:.2f}", "Mbps"


def format_bytes(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} GB"
    return f"{value / 1_000_000:.2f} MB"


def format_report(result: SpeedTestResult) -> str:
    download, download_unit = format_speed(result.download_mbps)
    upload, upload_unit = format_speed(result.upload_mbps)
    return "\n".join(
        (
            "FuzzToolBox 网络测速结果",
            f"延迟：{result.latency_ms:.1f} ms",
            f"抖动：{result.jitter_ms:.1f} ms",
            f"下载：{download} {download_unit}",
            f"上传：{upload} {upload_unit}",
            f"数据量：↓ {format_bytes(result.downloaded_bytes)}  ↑ {format_bytes(result.uploaded_bytes)}",
            f"耗时：{result.duration_seconds:.1f} 秒",
        )
    )


class SpeedMetricCard(QFrame):
    def __init__(self, title: str, accent: str = "normal"):
        super().__init__()
        self.setObjectName("speedMetricCard")
        self.setProperty("accent", accent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(5)
        heading = QLabel(title)
        heading.setObjectName("speedMetricTitle")
        layout.addWidget(heading)
        value_row = QHBoxLayout()
        value_row.setSpacing(7)
        value_row.setAlignment(Qt.AlignLeft | Qt.AlignBaseline)
        self.value = QLabel("—")
        self.value.setObjectName("speedMetricValue")
        self.unit = QLabel("")
        self.unit.setObjectName("speedMetricUnit")
        value_row.addWidget(self.value)
        value_row.addWidget(self.unit)
        value_row.addStretch()
        layout.addLayout(value_row)

    def set_value(self, value: str, unit: str) -> None:
        self.value.setText(value)
        self.unit.setText(unit)


class SpeedTestWorker(QThread):
    progress = Signal(str, float, float)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = SpeedTestEngine()

    def run(self) -> None:
        try:
            self.completed.emit(self.engine.run(self.progress.emit))
        except SpeedTestCancelled:
            self.failed.emit("测速已停止")
        except (OSError, TimeoutError, ValueError) as exc:
            self.failed.emit(f"测速失败：{exc}")

    def cancel(self) -> None:
        self.engine.cancel()


class SpeedTestPage(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.result = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(14)

        intro_row = QHBoxLayout()
        intro = QVBoxLayout()
        intro.setSpacing(4)
        heading = QLabel("检测当前网络的延迟、抖动、下载速度与上传速度")
        heading.setObjectName("speedHeading")
        subtitle = QLabel("测速将产生网络流量，测试过程中可随时停止")
        subtitle.setObjectName("speedSubtitle")
        intro.addWidget(heading)
        intro.addWidget(subtitle)
        intro_row.addLayout(intro)
        intro_row.addStretch()
        self.start_button = QPushButton("开始测速")
        self.start_button.setMinimumSize(112, 42)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("secondary")
        self.stop_button.setMinimumSize(82, 42)
        self.stop_button.setVisible(False)
        intro_row.addWidget(self.stop_button)
        intro_row.addWidget(self.start_button)
        root.addLayout(intro_row)

        self.hero = QFrame()
        self.hero.setObjectName("speedHero")
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(24, 20, 24, 21)
        hero_layout.setSpacing(10)
        state_row = QHBoxLayout()
        state_label = QLabel("实时速度")
        state_label.setObjectName("speedHeroCaption")
        self.phase_label = QLabel("准备就绪")
        self.phase_label.setObjectName("speedPhaseBadge")
        state_row.addWidget(state_label)
        state_row.addStretch()
        state_row.addWidget(self.phase_label)
        hero_layout.addLayout(state_row)
        value_row = QHBoxLayout()
        value_row.setSpacing(8)
        value_row.setAlignment(Qt.AlignLeft | Qt.AlignBaseline)
        self.live_value = QLabel("—")
        self.live_value.setObjectName("speedHeroValue")
        self.live_unit = QLabel("")
        self.live_unit.setObjectName("speedHeroUnit")
        value_row.addWidget(self.live_value)
        value_row.addWidget(self.live_unit)
        value_row.addStretch()
        hero_layout.addLayout(value_row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setObjectName("speedProgress")
        hero_layout.addWidget(self.progress)
        root.addWidget(self.hero)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.download_card = SpeedMetricCard("下载速度", "download")
        self.upload_card = SpeedMetricCard("上传速度", "upload")
        self.latency_card = SpeedMetricCard("网络延迟")
        self.jitter_card = SpeedMetricCard("网络抖动")
        metrics.addWidget(self.download_card, 0, 0)
        metrics.addWidget(self.upload_card, 0, 1)
        metrics.addWidget(self.latency_card, 1, 0)
        metrics.addWidget(self.jitter_card, 1, 1)
        metrics.setColumnStretch(0, 1)
        metrics.setColumnStretch(1, 1)
        root.addLayout(metrics)

        details = QFrame()
        details.setObjectName("speedDetails")
        details_layout = QHBoxLayout(details)
        details_layout.setContentsMargins(16, 11, 16, 11)
        self.traffic_label = QLabel("数据量  —")
        self.duration_label = QLabel("耗时  —")
        self.copy_button = QPushButton("复制结果")
        self.copy_button.setObjectName("secondary")
        self.copy_button.setEnabled(False)
        details_layout.addWidget(self.traffic_label)
        details_layout.addSpacing(20)
        details_layout.addWidget(self.duration_label)
        details_layout.addStretch()
        details_layout.addWidget(self.copy_button)
        root.addWidget(details)
        root.addStretch()

        apply_style(self, "tools.speed_test.page:root")
        self.start_button.clicked.connect(self.start_test)
        self.stop_button.clicked.connect(self.stop_test)
        self.copy_button.clicked.connect(self.copy_result)

    def start_test(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.result = None
        self.copy_button.setText("复制结果")
        self.copy_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setVisible(True)
        self.progress.setValue(0)
        self.phase_label.setText("正在检测延迟")
        self.live_value.setText("—")
        self.live_unit.setText("")
        set_style_state(self.hero, "running")
        self.worker = SpeedTestWorker(self)
        self.worker.progress.connect(self._update_progress)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def stop_test(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.stop_button.setEnabled(False)
            self.phase_label.setText("正在停止")
            self.worker.cancel()

    def _update_progress(self, phase: str, progress: float, value: float) -> None:
        phase_ranges = {
            "latency": (0, 20, "正在检测延迟"),
            "download": (20, 65, "正在测试下载"),
            "upload": (65, 100, "正在测试上传"),
        }
        if phase not in phase_ranges:
            return
        start, end, title = phase_ranges[phase]
        self.phase_label.setText(title)
        self.progress.setValue(round(start + (end - start) * progress))
        if phase == "latency":
            self.live_value.setText(f"{value:.1f}")
            self.live_unit.setText("ms")
        else:
            shown, unit = format_speed(value)
            self.live_value.setText(shown)
            self.live_unit.setText(unit)

    def _completed(self, result: SpeedTestResult) -> None:
        self.result = result
        download, download_unit = format_speed(result.download_mbps)
        upload, upload_unit = format_speed(result.upload_mbps)
        self.download_card.set_value(download, download_unit)
        self.upload_card.set_value(upload, upload_unit)
        self.latency_card.set_value(f"{result.latency_ms:.1f}", "ms")
        self.jitter_card.set_value(f"{result.jitter_ms:.1f}", "ms")
        self.live_value.setText(download)
        self.live_unit.setText(download_unit)
        self.traffic_label.setText(
            f"数据量  ↓ {format_bytes(result.downloaded_bytes)}  ↑ {format_bytes(result.uploaded_bytes)}"
        )
        self.duration_label.setText(f"耗时  {result.duration_seconds:.1f} 秒")
        self.phase_label.setText("测速完成")
        self.progress.setValue(100)
        self.copy_button.setEnabled(True)
        set_style_state(self.hero, "complete")

    def _failed(self, message: str) -> None:
        self.phase_label.setText(message)
        set_style_state(self.hero, "error")

    def _worker_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.start_button.setText("重新测速" if self.result is not None else "开始测速")
        self.stop_button.setEnabled(True)
        self.stop_button.setVisible(False)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def copy_result(self) -> None:
        if self.result is not None:
            QGuiApplication.clipboard().setText(format_report(self.result))
            self.copy_button.setText("已复制")

    def prepare_close(self, callback=None) -> bool:
        if self.worker is None or not self.worker.isRunning():
            return True
        self.worker.cancel()
        if callback is not None:
            self.worker.finished.connect(callback)
        return False
