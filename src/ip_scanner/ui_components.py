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
            painter.setBrush(QColor("#ecf5ff"))
            painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor("#303133"))
        painter.drawText(
            rect.adjusted(10, 0, -8, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            str(index.data()),
        )
        painter.restore()


def configure_combo(combo: QComboBox) -> None:
    """Apply the toolbox-wide dropdown interaction and visual style."""
    view = QListView(combo)
    view.setMouseTracking(True)
    view.setSpacing(0)
    view.setItemDelegate(ComboItemDelegate(view))
    combo.setView(view)


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
        painter.setPen(QColor("#e4e7ed"))
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
