"""Pass plan as a draggable chip row (design v3): numbered chips with a
remove ✕, drag to reorder, + buttons to append passes. The engine note
sits full-width below."""

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QListView,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from .i18n import tr

ENGINE_LABELS = {"whisper": "Whisper", "gigaam": "GigaAM"}

ENGINE_TIPS = {
    "whisper": ("Whisper: handles English and mixed-language speech well; "
                "slower; works out of the box, no extra setup."),
    "gigaam": ("GigaAM: faster and noticeably more accurate for pure Russian "
               "speech; weaker on mixed Russian/English (may mangle English "
               "words); requires a one-time Hugging Face setup."),
}

INFO_TEXT = ("Passes run top to bottom; each pass re-checks the previous "
             "pass's output and stops early once nothing new is found. "
             "Different engines catch words the other missed.")


class _Chip(QFrame):
    def __init__(self, number: int, engine: str, on_remove, parent=None):
        super().__init__(parent)
        self.setProperty("passChip", True)
        self.setToolTip(tr(ENGINE_TIPS[engine]))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 6, 3)
        layout.setSpacing(6)
        badge = QLabel(str(number))
        badge.setProperty("stepNumber", True)
        layout.addWidget(badge)
        layout.addWidget(QLabel(ENGINE_LABELS[engine]))
        remove = QToolButton()
        remove.setProperty("chipRemove", True)
        remove.setText("✕")
        remove.clicked.connect(on_remove)
        layout.addWidget(remove)
        self.setFixedSize(self.sizeHint())  # compact: content width only


class _ChipsList(QListWidget):
    """Notifies its owner on resize so the wrapped-chip height can be
    recomputed for the new width."""

    def __init__(self, on_resize, parent=None):
        self._on_resize = on_resize  # before super(): resize can fire early
        super().__init__(parent)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._on_resize()


class PassPlanWidget(QGroupBox):
    changed = Signal()
    MAX_VISIBLE_ROWS = 4  # taller plans scroll vertically

    def __init__(self, parent=None):
        super().__init__(tr("Pass plan"), parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # one pass per row (a vertical column, like the old plain list),
        # add buttons in their own column on the right
        row = QHBoxLayout()
        row.setSpacing(12)
        self.chips = _ChipsList(self._update_height)
        self.chips.setObjectName("pass_chips")
        self.chips.setSpacing(2)
        self.chips.setDragDropMode(QAbstractItemView.InternalMove)
        self.chips.setSelectionMode(QAbstractItemView.SingleSelection)
        self.chips.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chips.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chips.setFrameShape(QFrame.NoFrame)
        self.chips.setToolTip(tr(INFO_TEXT))
        # never force the window wider (e.g. when the scrollbar appears)
        from PySide6.QtWidgets import QSizePolicy
        self.chips.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.chips.setMinimumWidth(180)
        # item widgets do not survive an internal drag-move; rebuild
        # from the items' data once the move settles
        self.chips.model().rowsMoved.connect(
            lambda *_: QTimer.singleShot(0, self._on_reordered))
        row.addWidget(self.chips, stretch=1)

        buttons_col = QVBoxLayout()
        buttons_col.setSpacing(8)
        self.add_whisper = QPushButton("+ Whisper")
        self.add_whisper.setToolTip(tr(ENGINE_TIPS["whisper"]))
        self.add_whisper.clicked.connect(lambda: self.add_pass("whisper"))
        self.add_gigaam = QPushButton("+ GigaAM")
        self.add_gigaam.setToolTip(tr(ENGINE_TIPS["gigaam"]))
        self.add_gigaam.clicked.connect(lambda: self.add_pass("gigaam"))
        buttons_col.addWidget(self.add_whisper)
        buttons_col.addWidget(self.add_gigaam)
        buttons_col.addStretch()
        row.addLayout(buttons_col)
        layout.addLayout(row)

        note = QLabel(tr("GigaAM: faster, best for pure Russian.\n"
                         "Whisper: slower, handles English/mixed speech."))
        note.setWordWrap(True)
        note.setProperty("muted", True)
        layout.addWidget(note)
        self._update_height()

    # ---------------------------------------------------------- model
    def engines(self) -> list:
        return [self.chips.item(i).data(Qt.UserRole)
                for i in range(self.chips.count())]

    def set_engines(self, names) -> None:
        self.chips.clear()
        for name in names:
            if name in ENGINE_LABELS:
                self._append(name)
        self._rebuild()
        self.changed.emit()

    def add_pass(self, engine: str) -> None:
        self._append(engine)
        self._rebuild()
        self.changed.emit()

    def remove_pass(self, index: int) -> None:
        if 0 <= index < self.chips.count():
            self.chips.takeItem(index)
            self._rebuild()
            self.changed.emit()

    def move_pass(self, source: int, target: int) -> None:
        count = self.chips.count()
        if not (0 <= source < count and 0 <= target < count):
            return
        item = self.chips.takeItem(source)
        self.chips.insertItem(target, item)
        self._rebuild()
        self.changed.emit()

    # ---------------------------------------------------------- chips
    def _append(self, engine: str):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, engine)
        self.chips.addItem(item)

    def _on_reordered(self):
        self._rebuild()
        self.changed.emit()

    def _rebuild(self):
        for i in range(self.chips.count()):
            item = self.chips.item(i)
            engine = item.data(Qt.UserRole)
            chip = _Chip(i + 1, engine,
                         lambda _=False, it=item: self.remove_pass(
                             self.chips.row(it)))
            # the chip is fixed-size, so the list can't stretch it: it
            # stays compact and left-aligned within the full-width row
            item.setSizeHint(QSize(24, chip.height() + 6))
            self.chips.setItemWidget(item, chip)
        self._update_height()

    def _update_height(self):
        """Show every row up to MAX_VISIBLE_ROWS, then scroll."""
        spacing = self.chips.spacing()
        row_height = 40
        if self.chips.count():
            row_height = (self.chips.item(0).sizeHint().height()
                          + 2 * spacing)
        visible = max(1, min(self.chips.count(), self.MAX_VISIBLE_ROWS))
        self.chips.setFixedHeight(visible * row_height + 6)
