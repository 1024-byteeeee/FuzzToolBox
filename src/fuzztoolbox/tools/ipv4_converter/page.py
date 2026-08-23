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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.style_loader import apply_style, clear_style

from ...core.network_info import NetworkInfo
from .converter import convert_ipv4


class ConversionCard(QFrame):
    def __init__(self, title, copied, *, monospace=False):
        super().__init__()
        self.title = title
        self.value = "—"
        self.setObjectName("ipv4ValueCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 12, 12)
        layout.setSpacing(5)
        heading = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("ipv4ValueTitle")
        self.copy_button = QPushButton("复制")
        self.copy_button.setObjectName("ipv4ValueCopy")
        self.copy_button.setCursor(Qt.PointingHandCursor)
        self.copy_button.clicked.connect(lambda: copied(self))
        heading.addWidget(label)
        heading.addStretch()
        heading.addWidget(self.copy_button)
        layout.addLayout(heading)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("ipv4ValueText")
        self.value_label.setWordWrap(True)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if monospace:
            self.value_label.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value = value
        self.value_label.setText(value)


class IPv4ConverterPage(QWidget):
    def __init__(self, network_info: NetworkInfo):
        super().__init__()
        self.network_info = network_info
        self.result_rows = []
        self.result_cards = {}
        self._card_groups = []
        self._result_columns = 2
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("ipv4PageScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        apply_style(self.scroll_area, "tools.ipv4_converter.page:64")
        scroll_content = QWidget()
        scroll_content.setObjectName("ipv4ScrollContent")
        root = QVBoxLayout(scroll_content)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)
        root.setSizeConstraint(QLayout.SetMinimumSize)
        self.scroll_area.setWidget(scroll_content)
        outer.addWidget(self.scroll_area)

        self.network_label = QLabel(f"本机网络  {self.network_info.display_text()}")
        self.network_label.setObjectName("networkInfo")
        apply_style(self.network_label, "tools.ipv4_converter.page:79")
        self.network_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.network_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        root.addWidget(self.network_label)

        intro = QLabel("将单个 IPv4 地址转换为常用数值格式及 IPv4 映射 IPv6 地址")
        apply_style(intro, "tools.ipv4_converter.page:88")
        intro.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        root.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("converterPanel")
        apply_style(panel, "tools.ipv4_converter.page:94")
        form = QHBoxLayout(panel)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)
        label = QLabel("IPv4 地址")
        default_ip = self.network_info.ip if isinstance(self.network_info.ip, str) else ""
        self.input = QLineEdit(default_ip)
        self.input.setPlaceholderText("例如 192.168.1.1")
        label.setBuddy(self.input)
        self.convert_button = QPushButton("转换")
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("neutral")
        form.addWidget(label)
        form.addWidget(self.input, 1)
        form.addWidget(self.convert_button)
        form.addWidget(self.clear_button)
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        root.addWidget(panel)

        actions = QHBoxLayout()
        self.status = QLabel("请输入 IPv4 地址")
        self.copy_all_button = QPushButton("复制全部")
        self.copy_all_button.setObjectName("secondary")
        self.copy_all_button.setEnabled(False)
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(self.copy_all_button)
        root.addLayout(actions)

        self.results = QFrame()
        self.results.setObjectName("ipv4Results")
        apply_style(self.results, "tools.ipv4_converter.page:127")
        result_layout = QVBoxLayout(self.results)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(10)
        self.result_state = QLabel("输入 IPv4 地址后开始转换")
        self.result_state.setObjectName("ipv4State")
        self.result_state.setAlignment(Qt.AlignCenter)
        result_layout.addWidget(self.result_state)

        self.result_content = QWidget()
        content = QVBoxLayout(self.result_content)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)
        hero = QFrame()
        hero.setObjectName("ipv4Hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 16)
        hero_title = QLabel("IPv4 地址")
        hero_title.setObjectName("ipv4HeroTitle")
        hero_layout.addWidget(hero_title)
        self.hero_value = QLabel("—")
        self.hero_value.setObjectName("ipv4HeroValue")
        self.hero_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hero_layout.addWidget(self.hero_value)
        badges = QHBoxLayout()
        for text in ("32 位地址", "四个八位组"):
            badge = QLabel(text)
            badge.setObjectName("ipv4Badge")
            badges.addWidget(badge)
        badges.addStretch()
        hero_layout.addLayout(badges)
        content.addWidget(hero)

        octets = QFrame()
        octets.setObjectName("ipv4Group")
        octet_layout = QVBoxLayout(octets)
        octet_layout.setContentsMargins(14, 12, 14, 14)
        octet_title = QLabel("八位组")
        octet_title.setObjectName("ipv4GroupTitle")
        octet_layout.addWidget(octet_title)
        octet_row = QHBoxLayout()
        self.octet_labels = []
        for index in range(4):
            value = QLabel("—")
            value.setObjectName("ipv4Octet")
            value.setAlignment(Qt.AlignCenter)
            self.octet_labels.append(value)
            octet_row.addWidget(value, 1)
            if index < 3:
                dot = QLabel("·")
                dot.setObjectName("ipv4Dot")
                octet_row.addWidget(dot)
        octet_layout.addLayout(octet_row)
        content.addWidget(octets)

        numeric = self._make_group("数值表示", (("二进制", True), ("十进制", True), ("十六进制", True)))
        content.addWidget(numeric)
        mapped = self._make_group("IPv6 映射", (("IPv6", True), ("IPv6（简写）", True)))
        content.addWidget(mapped)
        content.addStretch()
        self.result_content.setVisible(False)
        result_layout.addWidget(self.result_content)
        self.results.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        root.addWidget(self.results, 1)

        self.input.returnPressed.connect(self.convert)
        self.convert_button.clicked.connect(self.convert)
        self.clear_button.clicked.connect(self.clear)
        self.copy_all_button.clicked.connect(self.copy_all)
        if self.input.text():
            self.convert()

    def _make_group(self, title, fields):
        group = QFrame()
        group.setObjectName("ipv4Group")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(9)
        heading = QLabel(title)
        heading.setObjectName("ipv4GroupTitle")
        layout.addWidget(heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        cards = []
        for index, (name, monospace) in enumerate(fields):
            card = ConversionCard(name, self._copy_card, monospace=monospace)
            self.result_cards[name] = card
            cards.append(card)
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        self._card_groups.append((grid, tuple(name for name, _ in fields)))
        return group

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 1 if event.size().width() < 820 else 2
        if columns == self._result_columns:
            return
        self._result_columns = columns
        for grid, names in self._card_groups:
            for name in names:
                grid.removeWidget(self.result_cards[name])
            for index, name in enumerate(names):
                grid.addWidget(self.result_cards[name], index // columns, index % columns)

    def convert(self):
        try:
            result = convert_ipv4(self.input.text())
        except ValueError as exc:
            self.result_rows = []
            self.result_content.setVisible(False)
            self.result_state.setText(f"无法转换\n{exc}")
            apply_style(self.result_state, "tools.ipv4_converter.page:259")
            self.result_state.setVisible(True)
            self.copy_all_button.setEnabled(False)
            self.status.setText(str(exc))
            return
        self.input.setText(result.ipv4)
        self.result_rows = list(result.rows())
        self.hero_value.setText(result.ipv4)
        for label, value in zip(self.octet_labels, result.ipv4.split(".")):
            label.setText(value)
        for name, value in self.result_rows:
            self.result_cards[name].set_value(value)
        self.result_state.setVisible(False)
        self.result_content.setVisible(True)
        self.copy_all_button.setEnabled(True)
        self.status.setText(f"已转换 {result.ipv4}")

    def clear(self):
        self.input.clear()
        self.result_rows = []
        self.result_content.setVisible(False)
        clear_style(self.result_state)
        self.result_state.setText("输入 IPv4 地址后开始转换")
        self.result_state.setVisible(True)
        self.copy_all_button.setEnabled(False)
        self.status.setText("请输入 IPv4 地址")
        self.input.setFocus()

    def _copy_card(self, card):
        if card.value == "—":
            return
        QGuiApplication.clipboard().setText(card.value)
        card.copy_button.setText("已复制")
        QTimer.singleShot(900, lambda: card.copy_button.setText("复制"))
        self.status.setText(f"已复制 · {card.title}")

    def copy_all(self):
        if not self.result_rows:
            return
        QGuiApplication.clipboard().setText(
            "\n".join(f"{name}: {value}" for name, value in self.result_rows)
        )
        self.status.setText("已复制全部转换结果")
