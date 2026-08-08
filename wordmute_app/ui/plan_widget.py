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
        layout.setContentsMargins(3, 3, 4, 3)
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


class PassPlanWidget(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(tr("Pass plan"), parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.chips = QListWidget()
        self.chips.setObjectName("pass_chips")
        self.chips.setFlow(QListView.LeftToRight)
        self.chips.setWrapping(True)
        self.chips.setDragDropMode(QAbstractItemView.InternalMove)
        self.chips.setSelectionMode(QAbstractItemView.SingleSelection)
        self.chips.setFixedHeight(46)
        self.chips.setFrameShape(QFrame.NoFrame)
        self.chips.setToolTip(tr(INFO_TEXT))
        # item widgets do not survive an internal drag-move; rebuild
        # from the items' data once the move settles
        self.chips.model().rowsMoved.connect(
            lambda *_: QTimer.singleShot(0, self._on_reordered))
        row.addWidget(self.chips, stretch=1)
        self.add_whisper = QPushButton("+ Whisper")
        self.add_whisper.setToolTip(tr(ENGINE_TIPS["whisper"]))
        self.add_whisper.clicked.connect(lambda: self.add_pass("whisper"))
        self.add_gigaam = QPushButton("+ GigaAM")
        self.add_gigaam.setToolTip(tr(ENGINE_TIPS["gigaam"]))
        self.add_gigaam.clicked.connect(lambda: self.add_pass("gigaam"))
        row.addWidget(self.add_whisper)
        row.addWidget(self.add_gigaam)
        layout.addLayout(row)

        note = QLabel(tr("GigaAM: faster, best for pure Russian.\n"
                         "Whisper: slower, handles English/mixed speech."))
        note.setWordWrap(True)
        note.setProperty("muted", True)
        layout.addWidget(note)

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
            item.setSizeHint(chip.sizeHint() + QSize(4, 4))
            self.chips.setItemWidget(item, chip)
