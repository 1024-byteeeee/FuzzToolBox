"""Screenshot tool launcher page."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from fuzztoolbox.tools.color_picker.eyedropper import (
    hide_window_instantly,
    native_window_is_visible,
    show_window_instantly,
)
from fuzztoolbox.ui.app_settings import create_settings
from fuzztoolbox.ui.components import KeepWindowSwitch
from fuzztoolbox.ui.style_loader import apply_style

from .overlay import ScreenshotOverlay


class ScreenshotPage(QWidget):
    def __init__(self):
        super().__init__()
        self._overlay = None
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)
        intro = QLabel("选择屏幕区域并使用画笔、图形、文字与马赛克完成截图标注")
        apply_style(intro, "tools.screenshot.page:intro")
        root.addWidget(intro)
        panel = QFrame()
        panel.setObjectName("screenshotLaunchPanel")
        apply_style(panel, "tools.screenshot.page:panel")
        content = QVBoxLayout(panel)
        content.setContentsMargins(32, 38, 32, 34)
        content.setSpacing(14)
        title = QLabel("截图与标注")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("screenshotLaunchTitle")
        content.addWidget(title)
        description = QLabel("拖动选择截图区域，完成后可复制到剪贴板或保存为 PNG 图片。")
        description.setAlignment(Qt.AlignCenter)
        description.setWordWrap(True)
        description.setObjectName("screenshotLaunchDescription")
        content.addWidget(description)
        button = QPushButton("开始截图")
        button.setFixedWidth(150)
        content.addWidget(button, 0, Qt.AlignCenter)
        self.keep_main_window = KeepWindowSwitch()
        self.keep_main_window.setChecked(
            create_settings().value(
                "capture/screenshot-keep-main", False, type=bool
            )
        )
        content.addWidget(self.keep_main_window, 0, Qt.AlignCenter)
        self.status = QLabel("准备就绪")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setObjectName("screenshotLaunchStatus")
        content.addWidget(self.status)
        root.addWidget(panel)
        root.addStretch()
        button.clicked.connect(self.start_capture)
        self.keep_main_window.toggled.connect(
            lambda checked: create_settings().setValue(
                "capture/screenshot-keep-main", checked
            )
        )
        self._restore_window_after_capture = False

    def start_capture(
        self,
        _checked=False,
        *,
        keep_main_window: bool | None = None,
        restore_main_window: bool = True,
    ):
        if self._overlay is not None:
            return
        self.status.setText("正在准备截图…")
        if keep_main_window is None:
            keep_main_window = self.keep_main_window.isChecked()
        main_window = self.window()
        should_hide_main_window = bool(main_window and not keep_main_window)
        self._restore_window_after_capture = bool(
            should_hide_main_window and restore_main_window
        )
        if should_hide_main_window:
            hide_window_instantly(main_window)
        overlay = ScreenshotOverlay(include_app_window=keep_main_window)
        self._overlay = overlay
        overlay.completed.connect(self._completed)
        overlay.cancelled.connect(self._cancelled)
        if keep_main_window:
            QTimer.singleShot(0, overlay.begin)
        else:
            self._wait_for_hide(overlay, main_window, time.monotonic())

    def _wait_for_hide(self, overlay, main_window, started_at):
        elapsed = time.monotonic() - started_at
        visible = native_window_is_visible(main_window)
        if elapsed >= 1.0 or (elapsed >= 0.35 and visible is not True):
            overlay.begin()
            return
        QTimer.singleShot(25, lambda: self._wait_for_hide(overlay, main_window, started_at))

    def _completed(self):
        self.status.setText("截图已完成")
        self._finish()

    def _cancelled(self):
        self.status.setText("已取消截图")
        self._finish()

    def _finish(self):
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None
        main_window = self.window()
        if main_window and self._restore_window_after_capture:
            show_window_instantly(main_window)
        self._restore_window_after_capture = False
