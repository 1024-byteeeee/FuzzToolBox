"""Searchable FuzzToolBox launcher page."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .tool_registry import TOOLS, ToolDefinition, filter_tools
from fuzztoolbox.ui.style_loader import apply_style


ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


class ToolCard(QFrame):
    activated = Signal(str)

    def __init__(self, tool: ToolDefinition):
        super().__init__()
        self.tool = tool
        self.setObjectName("toolCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(260, 154)
        self.setMaximumHeight(174)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(9)
        heading = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(40, 40)
        icon.setPixmap(QIcon(str(ASSET_DIR / tool.icon)).pixmap(40, 40))
        name = QLabel(tool.name)
        apply_style(name, "ui.home_page:46")
        heading.addWidget(icon)
        heading.addSpacing(7)
        heading.addWidget(name)
        heading.addStretch()
        layout.addLayout(heading)

        description = QLabel(tool.description)
        description.setWordWrap(True)
        apply_style(description, "ui.home_page:55")
        layout.addWidget(description)
        layout.addStretch()
        category = QLabel(tool.category)
        apply_style(category, "ui.home_page:59")
        layout.addWidget(category)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.tool.id)
        super().mouseReleaseEvent(event)


class ToolboxHomePage(QWidget):
    tool_requested = Signal(str)

    def __init__(self, tools=TOOLS):
        super().__init__()
        self.tools = tuple(tools)
        self.cards = {tool.id: ToolCard(tool) for tool in self.tools}
        self.category = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 20)
        root.setSpacing(16)
        self.title = QLabel("Fuzz Tool Box")
        apply_style(self.title, "ui.home_page:81")
        subtitle = QLabel("为 IT 工作准备的一站式桌面工具箱")
        apply_style(subtitle, "ui.home_page:83")
        root.addWidget(self.title)
        root.addWidget(subtitle)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索工具，例如 IP、Ping、端口…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(42)
        root.addWidget(self.search)

        categories = QHBoxLayout()
        categories.setSpacing(8)
        self.category_buttons = {}
        category_values = tuple(dict.fromkeys(tool.category for tool in self.tools))
        for label, value in (("全部", "all"), *((value, value) for value in category_values)):
            button = QPushButton(label)
            button.setObjectName("categoryButton")
            button.setCheckable(True)
            button.setChecked(value == "all")
            button.clicked.connect(
                lambda checked=False, selected=value: self.set_category(selected)
            )
            categories.addWidget(button)
            self.category_buttons[value] = button
        categories.addStretch()
        root.addLayout(categories)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.card_host = QWidget()
        self.card_grid = QGridLayout(self.card_host)
        self.card_grid.setContentsMargins(0, 4, 4, 4)
        self.card_grid.setHorizontalSpacing(14)
        self.card_grid.setVerticalSpacing(14)
        self.card_grid.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.card_host)
        root.addWidget(scroll, 1)

        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        apply_style(self.empty_label, "ui.home_page:126")
        root.addWidget(self.empty_label)

        for card in self.cards.values():
            card.activated.connect(self.tool_requested.emit)
        self.search.textChanged.connect(self.refresh_tools)
        self.refresh_tools()

    def set_category(self, category: str):
        self.category = category
        for value, button in self.category_buttons.items():
            button.setChecked(value == category)
        self.refresh_tools()

    def refresh_tools(self):
        visible = filter_tools(self.tools, self.search.text(), self.category)
        visible_ids = {tool.id for tool in visible}
        for card in self.cards.values():
            self.card_grid.removeWidget(card)
            card.setVisible(card.tool.id in visible_ids)
        columns = max(1, min(3, max(1, self.width() - 56) // 310))
        for index, tool in enumerate(visible):
            self.card_grid.addWidget(self.cards[tool.id], index // columns, index % columns)
        self.empty_label.setText("没有找到匹配的工具" if not visible else "")
        self.empty_label.setVisible(not visible)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_tools()
