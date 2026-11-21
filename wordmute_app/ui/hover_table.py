"""QTableWidget with whole-row hover highlight.

QSS can only hover single cells, which reads as broken; this tracks
the mouse and tints the entire hovered row with the theme's hover
color. Selection still paints over the hover tint."""

import contextlib

from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QHeaderView, QTableWidget

from .theme import hover_color


class HoverRowTable(QTableWidget):
    def __init__(self, rows: int = 0, columns: int = 0, parent=None):
        super().__init__(rows, columns, parent)
        self._hover_row = -1
        self.setMouseTracking(True)
        self.cellEntered.connect(lambda row, _col: self._set_hover(row))

    @contextlib.contextmanager
    def filling(self):
        """Fill many cells in one go: `with table.filling(): …setItem…`.

        A header section in ResizeToContents re-measures its WHOLE
        column after every single setItem, so a fill costs rows² —
        200 history records (1000 cells) took 3.5 s on every visit to
        the History tab, and the window froze for that long. Inside
        the block those sections are Fixed; on the way out they go
        back to ResizeToContents and are measured once. Stretch and
        Fixed sections are left alone."""
        header = self.horizontalHeader()
        fitted = [col for col in range(self.columnCount())
                  if header.sectionResizeMode(col)
                  == QHeaderView.ResizeToContents]
        for col in fitted:
            header.setSectionResizeMode(col, QHeaderView.Fixed)
        try:
            yield
        finally:
            for col in fitted:
                header.setSectionResizeMode(col,
                                            QHeaderView.ResizeToContents)

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
