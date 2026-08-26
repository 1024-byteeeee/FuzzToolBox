from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.style_loader import apply_style, clear_style
from fuzztoolbox.ui.tool_runtime import ToolActivity

from ...ui.components import configure_combo
from .converter import convert_datetime, convert_timestamp, current_result

GROUPS = (
    ("时间戳", ("Unix 时间戳（秒）", "Unix 时间戳（毫秒）", "Unix 时间戳（微秒）")),
    ("标准格式", ("ISO 8601", "RFC 3339", "RFC 2822", "HTTP 日期")),
    ("日期信息", ("UTC 日期时间", "带毫秒日期时间", "日期", "时间", "年积日", "ISO 周日期", "中文日期时间", "星期", "UTC 偏移")),
)


class ResultCard(QFrame):
    def __init__(self, name, copied):
        super().__init__()
        self.name = name
        self.value = "—"
        self.setObjectName("dateResultCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 12, 11)
        layout.setSpacing(5)
        heading = QHBoxLayout()
        title = QLabel(name)
        title.setObjectName("dateResultName")
        self.copy_button = QPushButton("复制")
        self.copy_button.setObjectName("dateCopyButton")
        self.copy_button.setCursor(Qt.PointingHandCursor)
        self.copy_button.clicked.connect(lambda: copied(self))
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(self.copy_button)
        layout.addLayout(heading)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("dateResultValue")
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value_label.setWordWrap(True)
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value = value
        self.value_label.setText(value)


class DateTimeConverterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.result_rows = []
        self.result_cards = {}
        self._card_grids = []
        self._card_columns = 2
        self._live_preview = True
        self._build_ui()
        self.live_timer = QTimer(self)
        self.live_timer.setInterval(100)
        self.live_timer.timeout.connect(self._update_live_preview)
        self._update_live_preview()
        self.live_timer.start()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)
        intro = QLabel("在 Unix 时间戳、ISO 8601 和常用日期时间格式之间转换")
        apply_style(intro, "tools.datetime_converter.page:70")
        root.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("datetimePanel")
        apply_style(panel, "tools.datetime_converter.page:75")
        form = QVBoxLayout(panel)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)
        options = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem("日期时间 → 时间戳", "datetime")
        self.mode.addItem("时间戳 → 日期时间", "timestamp")
        self.unit = QComboBox()
        for label, value in (("自动识别单位", "auto"), ("秒", "seconds"), ("毫秒", "milliseconds"), ("微秒", "microseconds")):
            self.unit.addItem(label, value)
        self.timezone = QComboBox()
        self.timezone.addItem("本地时区", "local")
        self.timezone.addItem("UTC", "UTC")
        self.timezone.addItem("自定义 UTC 偏移", "custom")
        for combo in (self.mode, self.unit, self.timezone):
            configure_combo(combo)
        self.offset = QLineEdit("UTC+08:00")
        self.offset.setPlaceholderText("例如 UTC+08:00")
        self.offset.setVisible(False)
        options.addWidget(QLabel("转换类型"))
        options.addWidget(self.mode)
        options.addWidget(QLabel("时间戳单位"))
        options.addWidget(self.unit)
        options.addWidget(QLabel("显示时区"))
        options.addWidget(self.timezone)
        options.addWidget(self.offset)
        options.addStretch()
        form.addLayout(options)

        entry = QHBoxLayout()
        self.input_label = QLabel("日期时间")
        self.input = QLineEdit()
        self.input.setPlaceholderText("例如 2026-04-13 17:00:00 或 ISO 8601")
        self.input.setClearButtonEnabled(True)
        self.convert_button = QPushButton("转换")
        self.now_button = QPushButton("使用当前时间")
        self.now_button.setObjectName("secondary")
        self.resume_live_button = QPushButton("恢复实时更新")
        self.resume_live_button.setObjectName("secondary")
        self.resume_live_button.setEnabled(False)
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("neutral")
        entry.addWidget(self.input_label)
        entry.addWidget(self.input, 1)
        entry.addWidget(self.convert_button)
        entry.addWidget(self.now_button)
        entry.addWidget(self.resume_live_button)
        entry.addWidget(self.clear_button)
        form.addLayout(entry)
        root.addWidget(panel)

        actions = QHBoxLayout()
        self.status = QLabel("等待输入")
        self.copy_all_button = QPushButton("复制全部")
        self.copy_all_button.setObjectName("secondary")
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(self.copy_all_button)
        root.addLayout(actions)

        self.results_scroll = QScrollArea()
        self.results_scroll.setObjectName("dateResultsScroll")
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setFrameShape(QFrame.NoFrame)
        results = QWidget()
        results.setObjectName("dateResults")
        results_layout = QVBoxLayout(results)
        results_layout.setContentsMargins(0, 0, 4, 0)
        results_layout.setSpacing(12)

        self.primary_card = ResultCard("标准日期时间", self._copy_card)
        self.primary_card.setObjectName("datePrimaryResult")
        results_layout.addWidget(self.primary_card)
        for group_name, names in GROUPS:
            group = QFrame()
            group.setObjectName("dateResultGroup")
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(14, 12, 14, 14)
            group_layout.setSpacing(9)
            title = QLabel(group_name)
            title.setObjectName("dateGroupTitle")
            group_layout.addWidget(title)
            cards = QGridLayout()
            cards.setHorizontalSpacing(10)
            cards.setVerticalSpacing(10)
            cards.setColumnStretch(0, 1)
            cards.setColumnStretch(1, 1)
            for index, name in enumerate(names):
                card = ResultCard(name, self._copy_card)
                self.result_cards[name] = card
                cards.addWidget(card, index // 2, index % 2)
            self._card_grids.append((cards, names))
            group_layout.addLayout(cards)
            results_layout.addWidget(group)
        results_layout.addStretch()
        self.results_scroll.setWidget(results)
        apply_style(self.results_scroll, "tools.datetime_converter.page:172")
        root.addWidget(self.results_scroll, 1)

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.timezone.currentIndexChanged.connect(self._timezone_changed)
        self.mode.activated.connect(self._stop_live_preview)
        self.unit.activated.connect(self._stop_live_preview)
        self.timezone.activated.connect(self._stop_live_preview)
        self.input.textEdited.connect(self._stop_live_preview)
        self.offset.textEdited.connect(self._stop_live_preview)
        self.input.returnPressed.connect(self._manual_convert)
        self.convert_button.clicked.connect(self._manual_convert)
        self.now_button.clicked.connect(self.use_current_time)
        self.resume_live_button.clicked.connect(self.resume_live_preview)
        self.clear_button.clicked.connect(self.clear)
        self.copy_all_button.clicked.connect(self.copy_all)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 1 if event.size().width() < 820 else 2
        if columns == self._card_columns:
            return
        self._card_columns = columns
        for grid, names in self._card_grids:
            for name in names:
                grid.removeWidget(self.result_cards[name])
            for index, name in enumerate(names):
                grid.addWidget(self.result_cards[name], index // columns, index % columns)

    def _timezone_value(self):
        return self.offset.text() if self.timezone.currentData() == "custom" else self.timezone.currentData()

    def _mode_changed(self):
        timestamp_mode = self.mode.currentData() == "timestamp"
        self.unit.setEnabled(timestamp_mode)
        self.input_label.setText("时间戳" if timestamp_mode else "日期时间")
        self.input.setPlaceholderText("输入 Unix 时间戳" if timestamp_mode else "例如 2026-04-13 17:00:00 或 ISO 8601")

    def _timezone_changed(self):
        self.offset.setVisible(self.timezone.currentData() == "custom")

    def _stop_live_preview(self, *_args):
        self._live_preview = False
        self.resume_live_button.setEnabled(True)
        if hasattr(self, "live_timer"):
            self.live_timer.stop()

    def resume_live_preview(self):
        self.mode.setCurrentIndex(self.mode.findData("datetime"))
        self.timezone.setCurrentIndex(self.timezone.findData("local"))
        self._live_preview = True
        self.resume_live_button.setEnabled(False)
        self._update_live_preview()
        self.live_timer.start()

    def _update_live_preview(self):
        if not self._live_preview:
            return
        result = current_result("local")
        local_now = result.display
        self.input.setText(local_now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
        self._set_results(result.rows())
        self.status.setText("当前本地时间 · 实时更新")
        apply_style(self.status, "tools.datetime_converter.page:251")

    def _manual_convert(self, *_args):
        self._stop_live_preview()
        self.convert()

    def runtime_activity(self) -> ToolActivity:
        if self.live_timer.isActive():
            return ToolActivity.running("正在实时更新当前本地时间")
        return ToolActivity()

    def prepare_close(self, _on_ready) -> bool:
        self.live_timer.stop()
        return True

    def convert(self):
        self._stop_live_preview()
        try:
            if self.mode.currentData() == "timestamp":
                result = convert_timestamp(self.input.text(), self.unit.currentData(), self._timezone_value())
            else:
                result = convert_datetime(self.input.text(), self._timezone_value())
        except ValueError as exc:
            self._set_results(())
            self.status.setText(str(exc))
            apply_style(self.status, "tools.datetime_converter.page:267")
            return
        self._set_results(result.rows())
        self.status.setText(f"转换成功 · {result.display.strftime('%Y-%m-%d %H:%M:%S %z')}")
        apply_style(self.status, "tools.datetime_converter.page:271")

    def use_current_time(self):
        self._stop_live_preview()
        try:
            result = current_result("local")
        except ValueError as exc:
            self._set_results(())
            self.status.setText(str(exc))
            apply_style(self.status, "tools.datetime_converter.page:280")
            return
        self.mode.setCurrentIndex(self.mode.findData("datetime"))
        self.input.setText(result.display.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
        self.convert()

    def clear(self):
        self._stop_live_preview()
        self.input.clear()
        self._set_results(())
        self.status.setText("等待输入")
        clear_style(self.status)
        self.input.setFocus()

    def _set_results(self, rows):
        self.result_rows = list(rows)
        values = dict(self.result_rows)
        self.primary_card.set_value(values.get("标准日期时间", "—"))
        for name, card in self.result_cards.items():
            card.set_value(values.get(name, "—"))

    def _copy_card(self, card):
        if card.value == "—":
            return
        QGuiApplication.clipboard().setText(card.value)
        card.copy_button.setText("已复制")
        QTimer.singleShot(900, lambda: card.copy_button.setText("复制"))
        self.status.setText(f"已复制 · {card.name}")

    def copy_all(self):
        if self.result_rows:
            QGuiApplication.clipboard().setText("\n".join(f"{name}: {value}" for name, value in self.result_rows))
            self.status.setText("已复制全部转换结果")
