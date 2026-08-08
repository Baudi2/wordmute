"""QTableWidget with whole-row hover highlight.

QSS can only hover single cells, which reads as broken; this tracks
the mouse and tints the entire hovered row with the theme's hover
color. Selection still paints over the hover tint."""

from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QTableWidget

from .theme import hover_color


class HoverRowTable(QTableWidget):
    def __init__(self, rows: int = 0, columns: int = 0, parent=None):
        super().__init__(rows, columns, parent)
        self._hover_row = -1
        self.setMouseTracking(True)
        self.cellEntered.connect(lambda row, _col: self._set_hover(row))

    def leaveEvent(self, event):
        self._set_hover(-1)
        super().leaveEvent(event)

    def setRowCount(self, rows: int):
        if rows < self.rowCount():
            self._hover_row = -1
        super().setRowCount(rows)

    def removeRow(self, row: int):
        self._hover_row = -1
        super().removeRow(row)

    def _paint_row(self, row: int, brush: QBrush):
        if 0 <= row < self.rowCount():
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item is not None:
                    item.setBackground(brush)

    def _set_hover(self, row: int):
        if row == self._hover_row:
            return
        self._paint_row(self._hover_row, QBrush())
        self._paint_row(row, QBrush(hover_color()))
        self._hover_row = row
