"""Sidebar navigation per the design update: a fixed-width icon list on
the left driving a QStackedWidget (deliberately not QTabWidget(West),
which rotates labels). Exposes a QTabWidget-like API so callers and
tests keep working: addTab / tabText / setTabText / count /
currentIndex / setCurrentWidget / widget / currentChanged."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class SidebarNav(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(200)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 8, 0, 8)
        self.nav = QListWidget()
        self.nav.setObjectName("nav_sidebar")
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.currentRowChanged.connect(self._on_row_changed)
        side_layout.addWidget(self.nav)
        layout.addWidget(side)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, stretch=1)

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.stack.setCurrentIndex(row)
            self.currentChanged.emit(row)

    # ------------------------------------------------ QTabWidget-like API
    def addTab(self, widget, title: str, icon=None) -> int:
        item = QListWidgetItem(title)
        if icon is not None:
            item.setIcon(icon)
        item.setSizeHint(QSize(0, 36))
        self.nav.addItem(item)
        self.stack.addWidget(widget)
        if self.nav.currentRow() < 0:
            self.nav.setCurrentRow(0)
        return self.nav.count() - 1

    def count(self) -> int:
        return self.nav.count()

    def tabText(self, index: int) -> str:
        item = self.nav.item(index)
        return item.text() if item else ""

    def setTabText(self, index: int, text: str) -> None:
        item = self.nav.item(index)
        if item:
            item.setText(text)

    def widget(self, index: int):
        return self.stack.widget(index)

    def currentIndex(self) -> int:
        return self.nav.currentRow()

    def setCurrentIndex(self, index: int) -> None:
        self.nav.setCurrentRow(index)

    def currentWidget(self):
        return self.stack.currentWidget()

    def setCurrentWidget(self, widget) -> None:
        index = self.stack.indexOf(widget)
        if index >= 0:
            self.nav.setCurrentRow(index)
