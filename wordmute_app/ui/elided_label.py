"""A QLabel whose full text never forces the layout's width."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    """Decorative hints and long values: paints itself elided (right by
    default; left when the tail matters more, e.g. a word-list pattern)
    and keeps the full text one hover away. A plain QLabel's minimum
    width IS its text — a long hint silently became the window's
    minimum width."""

    def __init__(self, text: str = "", parent=None, mode=Qt.ElideRight,
                 tooltip_full: bool = True):
        super().__init__(text, parent)
        self._mode = mode
        self._tooltip_full = tooltip_full
        self.setMinimumWidth(24)
        if tooltip_full:
            self.setToolTip(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        if self._tooltip_full:
            self.setToolTip(text)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), self._mode,
                                             rect.width())
        painter.drawText(rect, int(self.alignment()) | Qt.AlignVCenter,
                         text)
