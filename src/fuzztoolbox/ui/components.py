from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
)

from fuzztoolbox.ui.style_loader import apply_style, on_theme_changed, theme_color


class ComboItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(34)
        return size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        rect = option.rect.adjusted(4, 2, -4, -2)
        if option.state & (QStyle.State_MouseOver | QStyle.State_Selected):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme_color("primary_soft")))
            painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor(theme_color("text")))
        painter.drawText(
            rect.adjusted(10, 0, -8, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            str(index.data()),
        )
        painter.restore()


class ComboListView(QListView):
    """Dropdown view that also paints Qt's separate popup container."""

    def __init__(self, parent=None):
        super().__init__(parent)
        on_theme_changed(self.apply_theme_palette)

    def apply_theme_palette(self):
        palette = self.palette()
        palette.setColor(QPalette.Base, QColor(theme_color("surface")))
        palette.setColor(QPalette.Window, QColor(theme_color("surface")))
        palette.setColor(QPalette.Text, QColor(theme_color("text")))
        palette.setColor(QPalette.Highlight, QColor(theme_color("primary_soft")))
        palette.setColor(QPalette.HighlightedText, QColor(theme_color("text")))
        self.setPalette(palette)
        self.viewport().setPalette(palette)
        popup = self.window()
        popup_palette = popup.palette()
        for role in (QPalette.Base, QPalette.Button):
            popup_palette.setColor(role, QColor(theme_color("surface")))
        popup_palette.setColor(QPalette.Window, QColor("transparent"))
        popup_palette.setColor(QPalette.Text, QColor(theme_color("text")))
        popup.setPalette(popup_palette)
        self.viewport().update()

    def prepare_popup(self) -> None:
        """Configure the popup once, before its native window is first shown."""
        popup = self.window()
        if popup.property("fuzztoolboxPopupPrepared"):
            return
        self.apply_theme_palette()
        if not popup.windowFlags() & Qt.FramelessWindowHint:
            popup.setWindowFlag(Qt.FramelessWindowHint, True)
        popup.setAttribute(Qt.WA_TranslucentBackground, True)
        popup.setAttribute(Qt.WA_StyledBackground, True)
        popup.setAutoFillBackground(False)
        popup.setObjectName("comboPopupContainer")
        apply_style(popup, "ui.components:57")
        popup.setProperty("fuzztoolboxPopupPrepared", True)


def configure_combo(combo: QComboBox) -> None:
    """Apply the toolbox-wide dropdown interaction and visual style."""
    view = ComboListView(combo)
    view.setMouseTracking(True)
    view.setSpacing(0)
    view.setFrameShape(QListView.NoFrame)
    view.setAttribute(Qt.WA_StyledBackground, True)
    apply_style(view, "ui.components:71")
    view.setItemDelegate(ComboItemDelegate(view))
    view.apply_theme_palette()
    palette = view.palette()
    view.setAutoFillBackground(True)
    view.viewport().setPalette(palette)
    view.viewport().setAutoFillBackground(True)
    view.viewport().setAttribute(Qt.WA_StyledBackground, True)
    view.viewport().setAutoFillBackground(False)
    apply_style(view.viewport(), "ui.components:92")
    combo.setView(view)
    view.prepare_popup()


class GridCellDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        styled_option = QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)
        foreground = index.data(Qt.ForegroundRole)
        text_color = (
            foreground
            if isinstance(foreground, QColor)
            else styled_option.palette.color(QPalette.Text)
        )
        styled_option.palette.setColor(QPalette.HighlightedText, text_color)
        super().paint(painter, styled_option, index)
        painter.save()
        painter.setPen(QColor(theme_color("border_soft")))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.drawLine(option.rect.topRight(), option.rect.bottomRight())
        painter.restore()


def configure_table(table: QTableView) -> None:
    """Apply the common table selection, grid and header behavior."""
    table.setItemDelegate(GridCellDelegate(table))
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setSelectionBehavior(QAbstractItemView.SelectItems)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
