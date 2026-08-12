from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .generator import MAX_PORT, MIN_PORT, generate_random_port
from fuzztoolbox.ui.style_loader import apply_style


class RandomPortPage(QWidget):
    def __init__(self):
        super().__init__()
        self.current_port = generate_random_port()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        intro = QLabel("生成一个避开系统保留范围的随机 TCP / UDP 端口号")
        apply_style(intro, "tools.random_port.page:27")
        root.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("randomPortPanel")
        apply_style(panel, "tools.random_port.page:32")
        content = QVBoxLayout(panel)
        content.setContentsMargins(28, 34, 28, 30)
        content.setSpacing(14)

        heading = QLabel("随机端口")
        heading.setAlignment(Qt.AlignCenter)
        apply_style(heading, "tools.random_port.page:42")
        content.addWidget(heading)

        self.port_label = QLabel(str(self.current_port))
        self.port_label.setObjectName("randomPortValue")
        self.port_label.setAlignment(Qt.AlignCenter)
        self.port_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        apply_style(self.port_label, "tools.random_port.page:49")
        content.addWidget(self.port_label)

        range_label = QLabel(f"生成范围  {MIN_PORT}–{MAX_PORT}")
        range_label.setAlignment(Qt.AlignCenter)
        apply_style(range_label, "tools.random_port.page:58")
        content.addWidget(range_label)

        actions = QHBoxLayout()
        actions.addStretch()
        self.refresh_button = QPushButton("刷新")
        self.copy_button = QPushButton("复制")
        self.copy_button.setObjectName("secondary")
        self.refresh_button.setMinimumWidth(108)
        self.copy_button.setMinimumWidth(108)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.copy_button)
        actions.addStretch()
        content.addLayout(actions)

        self.status = QLabel("已生成随机端口")
        self.status.setAlignment(Qt.AlignCenter)
        apply_style(self.status, "tools.random_port.page:75")
        content.addWidget(self.status)
        root.addWidget(panel)

        note = QLabel("提示：随机生成不代表该端口当前未被其他程序占用。")
        note.setWordWrap(True)
        apply_style(note, "tools.random_port.page:81")
        root.addWidget(note)
        root.addStretch()

        self.refresh_button.clicked.connect(self.refresh_port)
        self.copy_button.clicked.connect(self.copy_port)

    def refresh_port(self):
        self.current_port = generate_random_port(self.current_port)
        self.port_label.setText(str(self.current_port))
        self.status.setText("已生成新的随机端口")

    def copy_port(self):
        QGuiApplication.clipboard().setText(str(self.current_port))
        self.status.setText(f"已复制端口 {self.current_port}")
