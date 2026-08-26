"""Screenshot tool launcher page."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from fuzztoolbox.tools.color_picker.eyedropper import (
    hide_window_instantly,
    native_window_is_visible,
)
from fuzztoolbox.ui.app_settings import create_settings
from fuzztoolbox.ui.app_state import ApplicationPreferences, CaptureKind
from fuzztoolbox.ui.components import KeepWindowSwitch
from fuzztoolbox.ui.style_loader import apply_style
from fuzztoolbox.ui.tool_runtime import ToolActivity

from .overlay import ScreenshotOverlay


class ScreenshotPage(QWidget):
    capture_requested = Signal(bool)

    def __init__(self, *, preferences: ApplicationPreferences | None = None):
        super().__init__()
        self._preferences = preferences or ApplicationPreferences(create_settings())
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
        self.capture_button = QPushButton("开始截图")
        self.capture_button.setFixedWidth(150)
        content.addWidget(self.capture_button, 0, Qt.AlignCenter)
        self.keep_main_window = KeepWindowSwitch()
        self.keep_main_window.setChecked(
            self._preferences.keep_main_window(CaptureKind.SCREENSHOT)
        )
        content.addWidget(self.keep_main_window, 0, Qt.AlignCenter)
        self.status = QLabel("准备就绪")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setObjectName("screenshotLaunchStatus")
        content.addWidget(self.status)
        root.addWidget(panel)
        root.addStretch()
        self.capture_button.clicked.connect(
            lambda _checked=False: self.capture_requested.emit(
                self.keep_main_window.isChecked()
            )
        )
        self.keep_main_window.toggled.connect(
            lambda checked: self._preferences.set_keep_main_window(
                CaptureKind.SCREENSHOT, checked
            )
        )
        self._hidden_capture_overlay = None

    def begin_capture(
        self,
        *,
        keep_main_window: bool,
    ) -> ScreenshotOverlay | None:
        """Start the overlay after the shell has acquired a capture session."""
        if self._overlay is not None:
            return None
        self.status.setText("正在准备截图…")
        main_window = self.window()
        should_hide_main_window = bool(main_window and not keep_main_window)
        if should_hide_main_window:
            hide_window_instantly(main_window)
        overlay = ScreenshotOverlay(include_app_window=keep_main_window)
        self._overlay = overlay
        overlay.completed.connect(self._completed)
        overlay.cancelled.connect(self._cancelled)
        overlay.capture_ready.connect(lambda: self._capture_ready(overlay))
        if keep_main_window:
            QTimer.singleShot(0, overlay.begin)
        else:
            self._wait_for_hide(overlay, main_window, time.monotonic())
        return overlay

    def _wait_for_hide(self, overlay, main_window, started_at):
        elapsed = time.monotonic() - started_at
        visible = native_window_is_visible(main_window)
        # AppKit can re-order a Qt window while the screenshot overlay is
        # becoming active. Re-issue orderOut during the settling window so a
        # regular shortcut capture never includes the FuzzToolBox window.
        if visible is True:
            hide_window_instantly(main_window)
        if elapsed >= 1.0 or (elapsed >= 0.35 and visible is not True):
            self._hidden_capture_overlay = overlay
            self._keep_main_hidden(overlay, main_window)
            overlay.begin()
            return
        QTimer.singleShot(25, lambda: self._wait_for_hide(overlay, main_window, started_at))

    def _keep_main_hidden(self, overlay, main_window):
        """Keep AppKit from reordering the main window during pixel capture."""
        if self._overlay is not overlay or self._hidden_capture_overlay is not overlay:
            return
        hide_window_instantly(main_window)
        QTimer.singleShot(
            25, lambda: self._keep_main_hidden(overlay, main_window)
        )

    def _capture_ready(self, overlay):
        if self._hidden_capture_overlay is overlay:
            self._hidden_capture_overlay = None

    def _completed(self):
        self.status.setText("截图已完成")
        self._finish()

    def _cancelled(self):
        self.status.setText("已取消截图")
        self._finish()

    def _finish(self):
        self._hidden_capture_overlay = None
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None

    def capture_blocked(self) -> None:
        self.status.setText("另一项屏幕捕获正在进行")

    def runtime_activity(self) -> ToolActivity:
        if self._overlay is not None:
            return ToolActivity.running("截图会话正在进行")
        return ToolActivity()

    def prepare_close(self, _on_ready) -> bool:
        if self._overlay is not None:
            self._overlay.cancel()
        return True
