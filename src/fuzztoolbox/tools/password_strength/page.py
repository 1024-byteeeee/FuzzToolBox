from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from .analyzer import analyze_password
from fuzztoolbox.ui.style_loader import apply_style, set_style_state


ASSET_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


class MetricCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("strengthMetric")
        apply_style(self, "tools.password_strength.page:26")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        heading = QLabel(title)
        apply_style(heading, "tools.password_strength.page:34")
        self.value = QLabel("—")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        apply_style(self.value, "tools.password_strength.page:37")
        layout.addWidget(heading)
        layout.addWidget(self.value)


class PasswordStrengthPage(QWidget):
    def __init__(self):
        super().__init__()
        self._password_visible = False
        self._build_ui()
        self.update_result("")

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        intro = QLabel("分析密码长度、熵、字符集、评分与预计暴力破解时长")
        apply_style(intro, "tools.password_strength.page:55")
        root.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("toolPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(14)

        password_label = QLabel("密码")
        apply_style(password_label, "tools.password_strength.page:65")
        panel_layout.addWidget(password_label)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("输入需要分析的密码")
        self.password_input.setMinimumHeight(46)
        self.password_input.setMaxLength(256)
        password_label.setBuddy(self.password_input)
        self.visibility_action = QAction(
            QIcon(str(ASSET_DIR / "eye-show.svg")), "显示密码", self.password_input
        )
        self.password_input.addAction(self.visibility_action, QLineEdit.TrailingPosition)
        self.visibility_action.triggered.connect(self.toggle_password_visibility)
        panel_layout.addWidget(self.password_input)

        score_row = QHBoxLayout()
        score_title = QLabel("强度分数")
        apply_style(score_title, "tools.password_strength.page:82")
        self.score_text = QLabel("0 / 100")
        apply_style(self.score_text, "tools.password_strength.page:84")
        score_row.addWidget(score_title)
        score_row.addStretch()
        score_row.addWidget(self.score_text)
        panel_layout.addLayout(score_row)

        self.score_bar = QProgressBar()
        self.score_bar.setRange(0, 100)
        self.score_bar.setTextVisible(False)
        self.score_bar.setFixedHeight(12)
        panel_layout.addWidget(self.score_bar)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.crack_time = MetricCard("预计暴力破解时长")
        self.length = MetricCard("密码长度")
        self.entropy = MetricCard("熵")
        self.charset = MetricCard("字符集大小")
        metrics.addWidget(self.crack_time, 0, 0, 1, 3)
        metrics.addWidget(self.length, 1, 0)
        metrics.addWidget(self.entropy, 1, 1)
        metrics.addWidget(self.charset, 1, 2)
        metrics.setColumnStretch(0, 1)
        metrics.setColumnStretch(1, 1)
        metrics.setColumnStretch(2, 1)
        panel_layout.addLayout(metrics)
        root.addWidget(panel)

        note = QLabel(
            "<b>注意：</b> 计算出的强度是基于使用暴力破解方法破解密码所需的时间，"
            "并未考虑到字典攻击的可能性。"
        )
        note.setWordWrap(True)
        apply_style(note, "tools.password_strength.page:118")
        root.addWidget(note)
        root.addStretch()

        self.password_input.textChanged.connect(self.update_result)

    def toggle_password_visibility(self):
        self._password_visible = not self._password_visible
        self.password_input.setEchoMode(
            QLineEdit.Normal if self._password_visible else QLineEdit.Password
        )
        icon = "eye-hide.svg" if self._password_visible else "eye-show.svg"
        label = "隐藏密码" if self._password_visible else "显示密码"
        self.visibility_action.setIcon(QIcon(str(ASSET_DIR / icon)))
        self.visibility_action.setText(label)
        self.visibility_action.setToolTip(label)

    def update_result(self, password: str):
        result = analyze_password(password)
        self.length.value.setText(str(result.length))
        self.charset.value.setText(str(result.charset_size))
        self.entropy.value.setText(f"{result.entropy:.2f} bits")
        self.crack_time.value.setText(result.crack_time)
        self.score_bar.setValue(result.score)
        self.score_text.setText(f"{result.score} / 100")
        state = "weak" if result.score < 25 else "fair" if result.score < 50 else "good" if result.score < 75 else "strong"
        set_style_state(self.score_text, state)
        set_style_state(self.score_bar, state)
