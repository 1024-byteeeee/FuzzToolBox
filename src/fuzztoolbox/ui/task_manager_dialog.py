"""Theme-aware dialog for loaded tool pages and active background tasks."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .style_loader import apply_style, set_style_state
from .tool_runtime import ToolRuntimeManager, ToolRuntimeState

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


class TaskManagerDialog(QDialog):
    open_requested = Signal(str)

    def __init__(self, runtime: ToolRuntimeManager, parent=None) -> None:
        super().__init__(parent)
        self.runtime = runtime
        self._signature = None
        self.setWindowTitle("任务管理器")
        self.setMinimumSize(640, 500)
        self.resize(680, 560)
        apply_style(self, "ui.task_manager_dialog:workspace")

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(12)
        title = QLabel("任务管理器")
        title.setObjectName("taskManagerTitle")
        root.addWidget(title)
        description = QLabel("查看并关闭所有已加载工具，以及正在运行的后台任务。")
        description.setObjectName("taskManagerDescription")
        root.addWidget(description)

        summary = QHBoxLayout()
        self.loaded_label = QLabel()
        self.loaded_label.setObjectName("taskManagerSummary")
        self.active_label = QLabel()
        self.active_label.setObjectName("taskManagerSummary")
        summary.addWidget(self.loaded_label)
        summary.addWidget(self.active_label)
        summary.addStretch()
        root.addLayout(summary)

        scroll = QScrollArea()
        scroll.setObjectName("taskManagerScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.rows_host = QWidget()
        self.rows_host.setObjectName("taskManagerRows")
        self.rows = QVBoxLayout(self.rows_host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(9)
        scroll.setWidget(self.rows_host)
        root.addWidget(scroll, 1)

        actions = QHBoxLayout()
        self.close_all_button = QPushButton("关闭全部工具")
        self.close_all_button.setObjectName("danger")
        self.close_button = QPushButton("完成")
        self.close_button.setObjectName("neutral")
        actions.addWidget(self.close_all_button)
        actions.addStretch()
        actions.addWidget(self.close_button)
        root.addLayout(actions)

        self.close_all_button.clicked.connect(
            lambda _checked=False: self.runtime.request_close_all()
        )
        self.close_button.clicked.connect(self.accept)
        self.runtime.changed.connect(self.refresh)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(400)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start()
        self.refresh()

    def refresh(self) -> None:
        snapshots = self.runtime.snapshots()
        signature = tuple(
            (item.tool_id, item.state.value, item.detail) for item in snapshots
        )
        self.loaded_label.setText(f"已加载 {len(snapshots)}")
        self.active_label.setText(
            f"正在运行 {sum(item.active for item in snapshots)}"
        )
        self.close_all_button.setEnabled(bool(snapshots))
        if signature == self._signature:
            return
        self._signature = signature
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not snapshots:
            empty = QLabel("当前没有已加载的工具")
            empty.setObjectName("taskManagerEmpty")
            empty.setAlignment(Qt.AlignCenter)
            self.rows.addWidget(empty, 1)
            return
        for snapshot in snapshots:
            self.rows.addWidget(self._make_row(snapshot))
        self.rows.addStretch()

    def _make_row(self, snapshot) -> QFrame:
        row = QFrame()
        row.setObjectName("taskManagerItem")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 12, 12, 12)
        layout.setSpacing(11)

        icon = QLabel()
        icon.setFixedSize(38, 38)
        icon.setPixmap(QIcon(str(ASSET_DIR / snapshot.icon)).pixmap(36, 36))
        layout.addWidget(icon)

        text = QVBoxLayout()
        text.setSpacing(3)
        heading = QHBoxLayout()
        name = QLabel(snapshot.name)
        name.setObjectName("taskManagerItemName")
        state = QLabel(
            {
                ToolRuntimeState.LOADED: "已加载",
                ToolRuntimeState.RUNNING: "运行中",
                ToolRuntimeState.STOPPING: "正在结束",
            }[snapshot.state]
        )
        state.setObjectName("taskManagerState")
        set_style_state(state, snapshot.state.value)
        heading.addWidget(name)
        heading.addWidget(state)
        heading.addStretch()
        detail = QLabel(snapshot.detail)
        detail.setObjectName("taskManagerItemDetail")
        detail.setWordWrap(True)
        text.addLayout(heading)
        text.addWidget(detail)
        layout.addLayout(text, 1)

        open_button = QPushButton("打开")
        open_button.setObjectName("secondary")
        open_button.setEnabled(snapshot.state is not ToolRuntimeState.STOPPING)
        open_button.clicked.connect(
            lambda _checked=False, tool_id=snapshot.tool_id: self._open(tool_id)
        )
        layout.addWidget(open_button)

        close_button = QPushButton(
            "结束任务" if snapshot.active else "关闭工具"
        )
        close_button.setObjectName(
            "danger" if snapshot.active else "neutral"
        )
        close_button.setEnabled(snapshot.state is not ToolRuntimeState.STOPPING)
        close_button.clicked.connect(
            lambda _checked=False, tool_id=snapshot.tool_id: self.runtime.request_close(
                tool_id
            )
        )
        layout.addWidget(close_button)
        return row

    def _open(self, tool_id: str) -> None:
        self.accept()
        self.open_requested.emit(tool_id)
