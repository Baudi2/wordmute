"""A layout that wraps its widgets onto the next line, like text.

Qt ships no wrapping box layout: a QHBoxLayout of chips just squeezes
them until the last ones are unreadable — which is what happened to the
Add-URL host chips once a paste covered five sites (the "…не похожи на
ссылки" warning came out clipped mid-word)."""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QSizePolicy


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    # ------------------------------------------------- QLayout plumbing
    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(),
                            margins.top() + margins.bottom())

    # ------------------------------------------------------------ core
    def _layout(self, rect, apply: bool) -> int:
        margins = self.contentsMargins()
        left = rect.x() + margins.left()
        top = rect.y() + margins.top()
        right = rect.right() - margins.right()
        x, y, line_height = left, top, 0
        for item in self._items:
            hint = item.sizeHint()
            if x > left and x + hint.width() > right:   # wrap
                x = left
                y += line_height + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


def make_chip(text: str, accent: str, warn: bool = False):
    """A pill with a leading dot, as in the design mock."""
    from PySide6.QtWidgets import QLabel
    chip = QLabel(f'<span style="color:{accent}">●</span> {text}')
    chip.setProperty("urlChip", True)
    chip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    if warn:
        chip.setProperty("state", "warn")
    return chip
