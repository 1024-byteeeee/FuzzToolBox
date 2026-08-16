from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .countdown import CountdownTimer, StopwatchTimer, format_duration
from fuzztoolbox.ui.style_loader import apply_style, set_style_state


class TimerPage(QWidget):
    PRESETS = (("1 分钟", 60), ("5 分钟", 300), ("10 分钟", 600), ("25 分钟", 1500), ("60 分钟", 3600))

    def __init__(self):
        super().__init__()
        self.timer_state = CountdownTimer(3602.004)
        self.stopwatch_state = StopwatchTimer()
        self.mode = "countdown"
        self._completion_notified = False
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(10)
        self.refresh_timer.timeout.connect(self.update_display)
        self._build_ui()
        self.control_shortcuts = []
        for key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(self.handle_control_shortcut)
            self.control_shortcuts.append(shortcut)
        self.update_display()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        intro = QLabel("支持精准倒计时与正计时，计时过程中切换页面或最小化窗口不会中断")
        apply_style(intro, "tools.timer.page:46")
        root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setObjectName("timerScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        apply_style(scroll, "tools.timer.page:scroll")
        scroll_content = QWidget()
        scroll_content.setObjectName("timerScrollContent")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("timerPanel")
        apply_style(panel, "tools.timer.page:51")
        content = QVBoxLayout(panel)
        content.setContentsMargins(26, 24, 26, 26)
        content.setSpacing(16)

        modes = QHBoxLayout()
        modes.addStretch()
        self.countdown_mode_button = QPushButton("倒计时")
        self.stopwatch_mode_button = QPushButton("正计时")
        for button in (self.countdown_mode_button, self.stopwatch_mode_button):
            button.setObjectName("categoryButton")
            button.setCheckable(True)
            button.setMinimumWidth(110)
            modes.addWidget(button)
        self.countdown_mode_button.setChecked(True)
        modes.addStretch()
        content.addLayout(modes)

        self.display = QLabel("01:00:02.004")
        self.display.setAlignment(Qt.AlignCenter)
        apply_style(self.display, "tools.timer.page:74")
        content.addWidget(self.display)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(12)
        content.addWidget(self.progress)

        self.status = QLabel("准备就绪")
        self.status.setAlignment(Qt.AlignCenter)
        apply_style(self.status, "tools.timer.page:88")
        content.addWidget(self.status)

        self.input_heading = QLabel("设置时长")
        apply_style(self.input_heading, "tools.timer.page:92")
        content.addWidget(self.input_heading)

        inputs = QHBoxLayout()
        inputs.setSpacing(12)
        inputs.addStretch()
        self.hours = self._make_spinbox(0, 99)
        self.minutes = self._make_spinbox(0, 59)
        self.seconds = self._make_spinbox(0, 59)
        self.milliseconds = self._make_spinbox(0, 999)
        self.hours.setValue(1)
        self.seconds.setValue(2)
        self.milliseconds.setValue(4)
        self.time_input_cards = []
        for label, field in (
            ("小时", self.hours),
            ("分钟", self.minutes),
            ("秒", self.seconds),
            ("毫秒", self.milliseconds),
        ):
            card = QFrame()
            self.time_input_cards.append(card)
            card.setObjectName("timeInputCard")
            card.setFixedWidth(154)
            apply_style(card, "tools.timer.page:116")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 12)
            card_layout.setSpacing(7)
            title = QLabel(label)
            apply_style(title, "tools.timer.page:124")
            card_layout.addWidget(title)
            card_layout.addWidget(field)
            inputs.addWidget(card)
        inputs.addStretch()
        content.addLayout(inputs)

        presets = QHBoxLayout()
        presets.setSpacing(8)
        self.preset_label = QLabel("快捷设置")
        presets.addWidget(self.preset_label)
        self.preset_buttons = []
        for label, seconds in self.PRESETS:
            button = QPushButton(label)
            button.setObjectName("categoryButton")
            button.clicked.connect(
                lambda checked=False, value=seconds: self.apply_preset(value)
            )
            self.preset_buttons.append(button)
            presets.addWidget(button)
        presets.addStretch()
        content.addLayout(presets)

        actions = QHBoxLayout()
        actions.addStretch()
        self.start_button = QPushButton("开始")
        self.pause_button = QPushButton("暂停")
        self.reset_button = QPushButton("重置")
        self.pause_button.setObjectName("secondary")
        self.reset_button.setObjectName("neutral")
        self.pause_button.setEnabled(False)
        for button in (self.start_button, self.pause_button, self.reset_button):
            button.setMinimumWidth(108)
            actions.addWidget(button)
        actions.addStretch()
        content.addLayout(actions)

        self.stopwatch_tip = QLabel("Tips：空格 & 回车均可控制开始按钮")
        self.stopwatch_tip.setAlignment(Qt.AlignCenter)
        apply_style(self.stopwatch_tip, "tools.timer.page:163")
        self.stopwatch_tip.setVisible(False)
        content.addWidget(self.stopwatch_tip)
        scroll_layout.addWidget(panel)
        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        self.hours.valueChanged.connect(self.duration_changed)
        self.minutes.valueChanged.connect(self.duration_changed)
        self.seconds.valueChanged.connect(self.duration_changed)
        self.milliseconds.valueChanged.connect(self.duration_changed)
        self.countdown_mode_button.clicked.connect(
            lambda checked=False: self.set_mode("countdown")
        )
        self.stopwatch_mode_button.clicked.connect(
            lambda checked=False: self.set_mode("stopwatch")
        )
        self.start_button.clicked.connect(self.start)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.reset_button.clicked.connect(self.reset)

    @staticmethod
    def _make_spinbox(minimum: int, maximum: int) -> QSpinBox:
        field = QSpinBox()
        field.setRange(minimum, maximum)
        field.setAlignment(Qt.AlignCenter)
        field.setMinimumHeight(44)
        field.setButtonSymbols(QAbstractSpinBox.NoButtons)
        field.setKeyboardTracking(False)
        field.lineEdit().setAlignment(Qt.AlignCenter)
        apply_style(field, "tools.timer.page:195")
        return field

    def set_mode(self, mode: str):
        if mode not in ("countdown", "stopwatch"):
            return
        self.refresh_timer.stop()
        self.timer_state.reset()
        self.stopwatch_state.reset()
        self.mode = mode
        countdown = mode == "countdown"
        self.countdown_mode_button.setChecked(countdown)
        self.stopwatch_mode_button.setChecked(not countdown)
        self.input_heading.setVisible(countdown)
        self.preset_label.setVisible(countdown)
        for widget in (*self.time_input_cards, *self.preset_buttons):
            widget.setVisible(countdown)
        self.progress.setVisible(countdown)
        self.pause_button.setVisible(countdown)
        self.stopwatch_tip.setVisible(not countdown)
        self._set_inputs_enabled(countdown)
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("暂停")
        self._set_stopwatch_action("idle")
        self.status.setText("准备就绪")
        self._completion_notified = False
        self.update_display()

    def handle_control_shortcut(self):
        if self.mode == "stopwatch":
            self.start()

    def handle_space_shortcut(self):
        """Backward-compatible alias for existing callers and tests."""
        self.handle_control_shortcut()

    def selected_seconds(self) -> float:
        return (
            self.hours.value() * 3600
            + self.minutes.value() * 60
            + self.seconds.value()
            + self.milliseconds.value() / 1000
        )

    def duration_changed(self):
        seconds = self.selected_seconds()
        if self.timer_state.state not in ("running", "paused"):
            self.timer_state.set_duration(seconds)
            self.status.setText("准备就绪" if seconds > 0 else "请设置计时时长")
            self.update_display()

    def apply_preset(self, seconds: int):
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        self.hours.blockSignals(True)
        self.minutes.blockSignals(True)
        self.seconds.blockSignals(True)
        self.milliseconds.blockSignals(True)
        self.hours.setValue(hours)
        self.minutes.setValue(minutes)
        self.seconds.setValue(secs)
        self.milliseconds.setValue(0)
        self.hours.blockSignals(False)
        self.minutes.blockSignals(False)
        self.seconds.blockSignals(False)
        self.milliseconds.blockSignals(False)
        self.timer_state.set_duration(seconds)
        self.update_display()

    def start(self):
        if self.mode == "stopwatch":
            if self.stopwatch_state.state == "idle":
                self.stopwatch_state.start()
                self._set_mode_buttons_enabled(False)
                self.status.setText("正计时中")
                self.refresh_timer.start()
                self._set_stopwatch_action("running")
            elif self.stopwatch_state.state == "running":
                self.stopwatch_state.pause()
                self.status.setText("已暂停")
                self._set_stopwatch_action("paused")
            elif self.stopwatch_state.state == "paused":
                self.stopwatch_state.resume()
                self.status.setText("正计时中")
                self._set_stopwatch_action("running")
            self.update_display()
            return
        seconds = self.selected_seconds()
        if seconds <= 0:
            QMessageBox.warning(self, "无法开始", "请设置大于 0 秒的计时时长。")
            return
        self.timer_state.set_duration(seconds)
        self.timer_state.start()
        self._completion_notified = False
        self._set_inputs_enabled(False)
        self._set_mode_buttons_enabled(False)
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.pause_button.setText("暂停")
        self.status.setText("计时中")
        self.refresh_timer.start()
        self.update_display()

    def toggle_pause(self):
        if self.mode == "stopwatch":
            if self.stopwatch_state.state == "running":
                self.stopwatch_state.pause()
                self.pause_button.setText("继续")
                self.status.setText("已暂停")
            elif self.stopwatch_state.state == "paused":
                self.stopwatch_state.resume()
                self.pause_button.setText("暂停")
                self.status.setText("正计时中")
            self.update_display()
            return
        if self.timer_state.state == "running":
            self.timer_state.pause()
            self.pause_button.setText("继续")
            self.status.setText("已暂停")
        elif self.timer_state.state == "paused":
            self.timer_state.resume()
            self.pause_button.setText("暂停")
            self.status.setText("计时中")
        self.update_display()

    def reset(self):
        self.refresh_timer.stop()
        self.timer_state.reset()
        self.stopwatch_state.reset()
        self._completion_notified = False
        self._set_inputs_enabled(self.mode == "countdown")
        self._set_mode_buttons_enabled(True)
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("暂停")
        self._set_stopwatch_action("idle")
        self.status.setText("准备就绪")
        self.update_display()

    def _set_inputs_enabled(self, enabled: bool):
        for widget in (
            self.hours,
            self.minutes,
            self.seconds,
            self.milliseconds,
            *self.preset_buttons,
        ):
            widget.setEnabled(enabled)

    def _set_mode_buttons_enabled(self, enabled: bool):
        self.countdown_mode_button.setEnabled(enabled)
        self.stopwatch_mode_button.setEnabled(enabled)

    def _set_stopwatch_action(self, state: str):
        if self.mode != "stopwatch":
            self.start_button.setText("开始")
            set_style_state(self.start_button, "countdown")
            return
        self.start_button.setText({"idle": "开始", "running": "暂停", "paused": "继续"}[state])
        set_style_state(self.start_button, state)

    def update_display(self):
        if self.mode == "stopwatch":
            self.display.setText(format_duration(self.stopwatch_state.elapsed))
            return
        remaining = self.timer_state.remaining
        self.display.setText(format_duration(remaining))
        self.progress.setValue(round(self.timer_state.progress * 1000))
        if self.timer_state.state == "finished" and not self._completion_notified:
            self._completion_notified = True
            self.refresh_timer.stop()
            self.status.setText("计时完成")
            self.pause_button.setEnabled(False)
            self.start_button.setEnabled(True)
            self._set_mode_buttons_enabled(True)
            QApplication.beep()
            QApplication.alert(self.window(), 3000)
            QMessageBox.information(self, "计时完成", "倒计时已结束。")
