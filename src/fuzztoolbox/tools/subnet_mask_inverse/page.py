from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...ui.style_loader import apply_style, set_style_state
from .converter import convert_mask


class ResultCard(QFrame):
    def __init__(self, title: str, copy_callback, *, wide=False):
        super().__init__()
        self.title = title
        self.value = "—"
        self.setObjectName("maskInverseCardWide" if wide else "maskInverseCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 12, 12)
        layout.setSpacing(5)
        heading = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("maskInverseCardTitle")
        self.copy_button = QPushButton("复制")
        self.copy_button.setObjectName("maskInverseCopy")
        self.copy_button.setCursor(Qt.PointingHandCursor)
        self.copy_button.clicked.connect(lambda: copy_callback(self))
        heading.addWidget(label)
        heading.addStretch()
        heading.addWidget(self.copy_button)
        layout.addLayout(heading)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("maskInverseCardValue")
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value_label.setWordWrap(True)
        if wide:
            self.value_label.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        layout.addWidget(self.value_label)

    def set_value(self, value: str):
        self.value = value
        self.value_label.setText(value)


class SubnetMaskInversePage(QWidget):
    def __init__(self):
        super().__init__()
        self.result_rows = []
        self.cards = {}
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("maskInverseWorkspace")
        apply_style(self, "tools.subnet_mask_inverse.page:workspace")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("maskInverseScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("maskInverseContent")
        root = QVBoxLayout(content)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)
        root.setSizeConstraint(QLayout.SetMinimumSize)
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)

        intro = QLabel("在子网掩码、通配符掩码与 CIDR 前缀之间快速换算")
        intro.setObjectName("maskInverseIntro")
        root.addWidget(intro)

        input_panel = QFrame()
        input_panel.setObjectName("maskInverseInputPanel")
        form = QHBoxLayout(input_panel)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)
        label = QLabel("掩码或 CIDR")
        self.input = QLineEdit("255.255.255.0")
        self.input.setPlaceholderText("例如 255.255.255.0、0.0.0.255 或 /24")
        label.setBuddy(self.input)
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("neutral")
        form.addWidget(label)
        form.addWidget(self.input, 1)
        form.addWidget(self.clear_button)
        root.addWidget(input_panel)

        actions = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("maskInverseStatus")
        self.copy_all_button = QPushButton("复制全部")
        self.copy_all_button.setObjectName("secondary")
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(self.copy_all_button)
        root.addLayout(actions)

        self.hero = QFrame()
        self.hero.setObjectName("maskInverseHero")
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_text = QVBoxLayout()
        hero_title = QLabel("识别结果")
        hero_title.setObjectName("maskInverseHeroTitle")
        self.hero_value = QLabel("—")
        self.hero_value.setObjectName("maskInverseHeroValue")
        hero_text.addWidget(hero_title)
        hero_text.addWidget(self.hero_value)
        hero_layout.addLayout(hero_text)
        hero_layout.addStretch()
        self.hero_badge = QLabel("—")
        self.hero_badge.setObjectName("maskInverseBadge")
        hero_layout.addWidget(self.hero_badge)
        root.addWidget(self.hero)

        result_panel = QFrame()
        result_panel.setObjectName("maskInverseResults")
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(14, 12, 14, 14)
        result_layout.setSpacing(10)
        title = QLabel("换算结果")
        title.setObjectName("maskInverseSectionTitle")
        result_layout.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        normal_fields = (
            "子网掩码", "通配符掩码", "CIDR 前缀", "网络位数",
            "主机位数", "地址总数", "可用主机数",
        )
        for index, name in enumerate(normal_fields):
            card = ResultCard(name, self._copy_card)
            self.cards[name] = card
            grid.addWidget(card, index // 2, index % 2)
        result_layout.addLayout(grid)
        for name in ("子网掩码（二进制）", "通配符掩码（二进制）"):
            card = ResultCard(name, self._copy_card, wide=True)
            self.cards[name] = card
            result_layout.addWidget(card)
        root.addWidget(result_panel)
        root.addStretch()

        self.input.textChanged.connect(self.convert)
        self.clear_button.clicked.connect(self.clear)
        self.copy_all_button.clicked.connect(self.copy_all)
        self.convert()

    def convert(self):
        try:
            result = convert_mask(self.input.text())
        except ValueError as exc:
            self.result_rows = []
            self.status.setText(str(exc))
            set_style_state(self.status, "error")
            self.hero_value.setText("等待有效输入")
            self.hero_badge.setText("输入有误")
            self.copy_all_button.setEnabled(False)
            for card in self.cards.values():
                card.set_value("—")
            return
        self.result_rows = list(result.rows())
        for name, value in self.result_rows:
            self.cards[name].set_value(value)
        self.hero_value.setText(f"{result.subnet_mask}  ↔  {result.wildcard_mask}")
        self.hero_badge.setText(f"{result.input_type} · /{result.prefix}")
        self.status.setText("已实时换算")
        set_style_state(self.status, "success")
        self.copy_all_button.setEnabled(True)

    def clear(self):
        self.input.clear()
        self.input.setFocus()

    def _copy_card(self, card):
        if card.value == "—":
            return
        QGuiApplication.clipboard().setText(card.value)
        card.copy_button.setText("已复制")
        QTimer.singleShot(900, lambda: card.copy_button.setText("复制"))
        self.status.setText(f"已复制 {card.title}")

    def copy_all(self):
        if not self.result_rows:
            return
        QGuiApplication.clipboard().setText(
            "\n".join(f"{name}: {value}" for name, value in self.result_rows)
        )
        self.status.setText("已复制全部换算结果")
