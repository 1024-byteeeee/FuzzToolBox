"""Plain-text editor with a synchronized line-number gutter."""

from typing import Optional

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget


class LineNumberArea(QWidget):
    def __init__(self, editor: "LineNumberEditor"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_number_area(event)


class LineNumberEditor(QPlainTextEdit):
    """QPlainTextEdit that paints logical block numbers outside the document."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self._error_line: Optional[int] = None
        self._decorations = []
        self._line_markers = {}
        self._empty_line_markers = {}
        self._highlight_read_only_line = False
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width()
        self.highlight_current_line()

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _block_count: int = 0):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect: QRect, dy: int):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        contents = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(contents.left(), contents.top(), self.line_number_area_width(), contents.height())
        )

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._empty_line_markers:
            return
        painter = QPainter(self.viewport())
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        marker_width = max(12, self.fontMetrics().horizontalAdvance("  "))
        marker_height = max(3, self.fontMetrics().height() // 4)
        x = round(self.contentOffset().x()) + 4
        while block.isValid() and top <= event.rect().bottom():
            bottom = top + round(self.blockBoundingRect(block).height())
            line = block.blockNumber() + 1
            color = self._empty_line_markers.get(line)
            if color and block.isVisible() and bottom >= event.rect().top():
                y = top + max(0, (bottom - top - marker_height) // 2)
                painter.fillRect(x, y, marker_width, marker_height, QColor(color))
            block = block.next()
            top = bottom

    def paint_line_number_area(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#f2f5f9"))
        painter.setPen(QColor("#d8dee8"))
        painter.drawLine(
            self.line_number_area.width() - 1,
            event.rect().top(),
            self.line_number_area.width() - 1,
            event.rect().bottom(),
        )

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current_line = self.textCursor().blockNumber() + 1
        while block.isValid() and top <= event.rect().bottom():
            line = block_number + 1
            if block.isVisible() and bottom >= event.rect().top():
                marker = self._line_markers.get(line)
                if marker:
                    painter.fillRect(0, top, 4, bottom - top, QColor(marker))
                if line == self._error_line:
                    painter.fillRect(0, top, self.line_number_area.width() - 1, bottom - top, QColor("#fde2e2"))
                    color = QColor("#d64545")
                elif line == current_line and self.hasFocus():
                    painter.fillRect(0, top, self.line_number_area.width() - 1, bottom - top, QColor("#e8f3ff"))
                    color = QColor("#1677d2")
                else:
                    color = QColor("#909399")
                painter.setPen(color)
                painter.drawText(
                    4,
                    top,
                    self.line_number_area.width() - 10,
                    self.fontMetrics().height(),
                    Qt.AlignRight,
                    str(line),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.highlight_current_line()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.highlight_current_line()

    def highlight_current_line(self):
        selections = []
        current_line_selection = None
        if not self.isReadOnly() or self._highlight_read_only_line:
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(64, 158, 255, 54 if self.isReadOnly() else 24))
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            current_line_selection = selection
        if current_line_selection is not None and not self._highlight_read_only_line:
            selections.append(current_line_selection)
        selections.extend(self._decorations)
        # In read-only Diff views the translucent current-line tint is painted
        # last so clicking a line remains visible over semantic Diff colors.
        if current_line_selection is not None and self._highlight_read_only_line:
            selections.append(current_line_selection)
        self.setExtraSelections(selections)
        self.line_number_area.update()

    def set_decorations(self, selections):
        self._decorations = list(selections)
        self.highlight_current_line()

    def clear_decorations(self):
        self.set_decorations([])

    def set_line_markers(self, markers):
        self._line_markers = dict(markers)
        self.line_number_area.update()

    def clear_line_markers(self):
        self.set_line_markers({})

    def set_empty_line_markers(self, markers):
        self._empty_line_markers = dict(markers)
        self.viewport().update()

    def clear_empty_line_markers(self):
        self.set_empty_line_markers({})

    def set_read_only_current_line_highlight(self, enabled):
        self._highlight_read_only_line = bool(enabled)
        self.highlight_current_line()

    def set_error_line(self, line: Optional[int]):
        self._error_line = line if line and line > 0 else None
        self.line_number_area.update()

    def clear_error_line(self):
        self.set_error_line(None)
