"""Searchable FuzzToolBox launcher page."""

from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QPainter
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

from fuzztoolbox.ui.style_loader import apply_style, current_theme

from .animations import FAST_DURATION
from .tool_registry import TOOLS, ToolDefinition, filter_tools

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


class ThemeToggleButton(QPushButton):
    """Borderless theme control with a subtle, reversible icon-size animation."""

    NORMAL_ICON_SIZE = QSize(23, 23)
    HOVER_ICON_SIZE = QSize(28, 28)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(self.NORMAL_ICON_SIZE)
        self._icon_animation = QPropertyAnimation(self, b"iconSize", self)
        self._icon_animation.setDuration(160)
        self._icon_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._hover_tooltip = QLabel(
            "",
            self,
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus,
        )
        self._hover_tooltip.setObjectName("headerActionTooltip")
        self._hover_tooltip.setAttribute(Qt.WA_ShowWithoutActivating)
        self._hover_tooltip.setAttribute(Qt.WA_TransparentForMouseEvents)
        apply_style(self._hover_tooltip, "ui.home_page:header_tooltip")
        self._hover_tooltip.hide()

    def event(self, event):
        if event.type() == QEvent.Enter:
            self._animate_icon(self.HOVER_ICON_SIZE)
        elif event.type() == QEvent.Leave:
            self._animate_icon(self.NORMAL_ICON_SIZE)
            self._hover_tooltip.hide()
        elif event.type() == QEvent.ToolTip:
            self._show_hover_tooltip()
            return True
        return super().event(event)

    def _animate_icon(self, target: QSize):
        self._icon_animation.stop()
        self._icon_animation.setStartValue(self.iconSize())
        self._icon_animation.setEndValue(target)
        self._icon_animation.start()

    def _show_hover_tooltip(self) -> None:
        text = self.toolTip()
        if not text:
            return
        self._hover_tooltip.setText(text)
        self._hover_tooltip.adjustSize()
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        position = self._tooltip_position(
            cursor,
            self._hover_tooltip.size(),
            screen.availableGeometry(),
        )
        self._hover_tooltip.move(position)
        self._hover_tooltip.show()

    @staticmethod
    def _tooltip_position(cursor, tooltip_size, available):
        gap_x, gap_y = 8, 12
        x = cursor.x() + gap_x
        y = cursor.y() + gap_y
        if x + tooltip_size.width() > available.right() + 1:
            x = cursor.x() - tooltip_size.width() - gap_x
        if y + tooltip_size.height() > available.bottom() + 1:
            y = cursor.y() - tooltip_size.height() - gap_y
        x = max(available.left(), min(x, available.right() - tooltip_size.width() + 1))
        y = max(available.top(), min(y, available.bottom() - tooltip_size.height() + 1))
        return QPoint(x, y)

class SettingsButton(ThemeToggleButton):
    """Settings control with the same smooth hover scaling as the theme button."""


class TaskManagerButton(ThemeToggleButton):
    """Task manager control with a compact loaded-tool count badge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 0

    def set_count(self, count: int) -> None:
        count = max(0, int(count))
        if count == self._count:
            return
        self._count = count
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._count <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f56c6c"))
        diameter = 16
        painter.drawEllipse(self.width() - diameter - 2, 2, diameter, diameter)
        painter.setPen(Qt.white)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        text = "9+" if self._count > 9 else str(self._count)
        painter.drawText(
            self.width() - diameter - 2,
            2,
            diameter,
            diameter,
            Qt.AlignCenter,
            text,
        )


class FavoriteButton(QPushButton):
    """Compact heart control with theme-aware icons and click feedback."""

    NORMAL_ICON_SIZE = QSize(20, 20)
    ACTIVE_ICON_SIZE = QSize(25, 25)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("favoriteButton")
        self.setCheckable(True)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(self.NORMAL_ICON_SIZE)
        self._animation = QPropertyAnimation(self, b"iconSize", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self.clicked.connect(self._animate_click)
        self.refresh_icon()

    def setChecked(self, checked):
        super().setChecked(checked)
        self.refresh_icon()

    def refresh_icon(self):
        if self.isChecked():
            name = "favorite-filled.svg"
        else:
            name = "favorite-outline-dark.svg" if current_theme() == "dark" else "favorite-outline.svg"
        self.setIcon(QIcon(str(ASSET_DIR / name)))
        self.setToolTip("取消收藏" if self.isChecked() else "添加到收藏")

    def _animate_click(self):
        self.refresh_icon()
        self._animation.stop()
        self._animation.setStartValue(self.ACTIVE_ICON_SIZE)
        self._animation.setEndValue(self.NORMAL_ICON_SIZE)
        self._animation.start()


class ToolCard(QFrame):
    activated = Signal(str)
    favorite_toggled = Signal(str, bool)

    def __init__(self, tool: ToolDefinition, parent=None):
        super().__init__(parent)
        self.tool = tool
        self.setObjectName("toolCard")
        self.setFocusPolicy(Qt.ClickFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(260, 154)
        self.setMaximumHeight(174)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        self._content_layout = layout
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(9)
        heading = QHBoxLayout()
        self.icon = QLabel()
        self.icon.setFixedSize(44, 44)
        self._tool_icon = QIcon(str(ASSET_DIR / tool.icon))
        self.icon.setPixmap(self._tool_icon.pixmap(40, 40))
        self.icon.setAlignment(Qt.AlignCenter)
        name = QLabel(tool.name)
        apply_style(name, "ui.home_page:46")
        heading.addWidget(self.icon)
        heading.addSpacing(7)
        heading.addWidget(name)
        heading.addStretch()
        self.favorite_button = FavoriteButton(self)
        self.favorite_button.clicked.connect(
            lambda checked: self.favorite_toggled.emit(self.tool.id, checked)
        )
        heading.addWidget(self.favorite_button)
        layout.addLayout(heading)

        description = QLabel(tool.description)
        description.setWordWrap(True)
        apply_style(description, "ui.home_page:55")
        layout.addWidget(description)
        layout.addStretch()
        category = QLabel(tool.category)
        apply_style(category, "ui.home_page:59")
        layout.addWidget(category)

        self._hovered = False
        self._motion_value = 0.0
        self._motion = QVariantAnimation(self)
        self._motion.setDuration(FAST_DURATION)
        self._motion.setEasingCurve(QEasingCurve.OutCubic)
        self._motion.valueChanged.connect(self._apply_motion)

    def set_favorite(self, favorite: bool):
        self.favorite_button.setChecked(favorite)

    def enterEvent(self, event):
        self._hovered = True
        self._animate_motion(2.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._animate_motion(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._animate_motion(-1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.tool.id)
        self._animate_motion(2.0 if self._hovered else 0.0)
        super().mouseReleaseEvent(event)

    def _animate_motion(self, target: float):
        self._motion.stop()
        self._motion.setStartValue(self._motion_value)
        self._motion.setEndValue(target)
        self._motion.start()

    def _apply_motion(self, value):
        self._motion_value = float(value)
        offset = self._motion_value
        self._content_layout.setContentsMargins(18, round(18 - offset), 18, round(16 + offset))
        icon_size = round(40 + max(0.0, offset) * 1.5)
        self.icon.setPixmap(self._tool_icon.pixmap(icon_size, icon_size))


class ToolboxHomePage(QWidget):
    tool_requested = Signal(str)
    theme_requested = Signal()
    settings_requested = Signal()
    tasks_requested = Signal()
    favorite_changed = Signal(str, bool)

    def __init__(self, tools=TOOLS, favorite_ids=()):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.tools = tuple(tools)
        valid_ids = {tool.id for tool in self.tools}
        self.favorite_ids = {tool_id for tool_id in favorite_ids if tool_id in valid_ids}
        self.category = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 2)
        root.setSpacing(16)
        heading = QHBoxLayout()
        self.title = QLabel("Fuzz Tool Box")
        apply_style(self.title, "ui.home_page:81")
        self.theme_button = ThemeToggleButton()
        self.theme_button.setObjectName("themeToggle")
        self.theme_button.setToolTip("切换界面主题")
        self.theme_button.setFixedSize(42, 42)
        self.theme_button.clicked.connect(self.theme_requested.emit)
        self.settings_button = SettingsButton()
        self.settings_button.setObjectName("themeToggle")
        self.settings_button.setToolTip("设置\n配置快捷键和工具选项")
        self.settings_button.setFixedSize(42, 42)
        self.settings_button.setIconSize(QSize(24, 24))
        self.settings_button.clicked.connect(self.settings_requested.emit)
        self.tasks_button = TaskManagerButton()
        self.tasks_button.setObjectName("themeToggle")
        self.tasks_button.setToolTip("任务管理器\n管理已加载和正在运行的工具")
        self.tasks_button.setFixedSize(42, 42)
        self.tasks_button.setIconSize(QSize(24, 24))
        self.tasks_button.clicked.connect(self.tasks_requested.emit)
        heading.addWidget(self.title)
        heading.addStretch()
        heading.addWidget(self.theme_button)
        heading.addWidget(self.tasks_button)
        heading.addWidget(self.settings_button)
        subtitle = QLabel("为 IT 工作准备的一站式桌面工具箱")
        apply_style(subtitle, "ui.home_page:83")
        root.addLayout(heading)
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
        for label, value in (
            ("全部", "all"),
            ("收藏", "favorites"),
            *((value, value) for value in category_values),
        ):
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
        scroll.setFocusPolicy(Qt.ClickFocus)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.card_host = QWidget()
        self.card_host.setFocusPolicy(Qt.ClickFocus)
        self.card_grid = QGridLayout(self.card_host)
        self.card_grid.setContentsMargins(0, 4, 4, 4)
        self.card_grid.setHorizontalSpacing(14)
        self.card_grid.setVerticalSpacing(14)
        self.card_grid.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.card_host)
        root.addWidget(scroll, 1)

        # Cards must have a parent before refresh_tools() makes them visible.
        # Otherwise Qt treats each parentless card as a temporary top-level
        # window, which produces a visible startup flash on Windows.
        self.cards = {
            tool.id: ToolCard(tool, self.card_host) for tool in self.tools
        }

        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        apply_style(self.empty_label, "ui.home_page:126")
        root.addWidget(self.empty_label)

        for card in self.cards.values():
            card.activated.connect(self.tool_requested.emit)
            card.favorite_toggled.connect(self._favorite_toggled)
            card.set_favorite(card.tool.id in self.favorite_ids)
        self.search.textChanged.connect(self.refresh_tools)
        self.refresh_tools()

    def _favorite_toggled(self, tool_id: str, favorite: bool):
        if favorite:
            self.favorite_ids.add(tool_id)
        else:
            self.favorite_ids.discard(tool_id)
        self.cards[tool_id].set_favorite(favorite)
        self.favorite_changed.emit(tool_id, favorite)
        if self.category == "favorites":
            self.refresh_tools()

    def refresh_favorite_icons(self):
        for card in self.cards.values():
            card.favorite_button.refresh_icon()

    def set_category(self, category: str):
        self.category = category
        for value, button in self.category_buttons.items():
            button.setChecked(value == category)
        self.refresh_tools()

    def refresh_tools(self):
        filter_category = "all" if self.category == "favorites" else self.category
        visible = filter_tools(self.tools, self.search.text(), filter_category)
        if self.category == "favorites":
            visible = tuple(tool for tool in visible if tool.id in self.favorite_ids)
        visible_ids = {tool.id for tool in visible}
        for card in self.cards.values():
            self.card_grid.removeWidget(card)
            card.setVisible(card.tool.id in visible_ids)
        columns = max(1, min(3, max(1, self.width() - 56) // 310))
        for index, tool in enumerate(visible):
            self.card_grid.addWidget(self.cards[tool.id], index // columns, index % columns)
        if visible:
            empty_text = ""
        elif self.category == "favorites" and not self.favorite_ids:
            empty_text = "还没有收藏工具"
        else:
            empty_text = "没有找到匹配的工具"
        self.empty_label.setText(empty_text)
        self.empty_label.setVisible(not visible)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_tools()
