"""Pass plan builder: an ordered list of engine passes with add /
remove / reorder controls."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

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


class PassPlanWidget(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Pass plan", parent)
        layout = QHBoxLayout(self)

        self.list = QListWidget()
        self.list.setToolTip(INFO_TEXT)
        layout.addWidget(self.list, stretch=1)

        buttons = QVBoxLayout()
        self.add_whisper = QPushButton("Add Whisper pass")
        self.add_whisper.setToolTip(ENGINE_TIPS["whisper"])
        self.add_whisper.clicked.connect(lambda: self.add_pass("whisper"))
        self.add_gigaam = QPushButton("Add GigaAM pass")
        self.add_gigaam.setToolTip(ENGINE_TIPS["gigaam"])
        self.add_gigaam.clicked.connect(lambda: self.add_pass("gigaam"))
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_selected)
        self.up_button = QPushButton("Move Up")
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button = QPushButton("Move Down")
        self.down_button.clicked.connect(lambda: self.move_selected(1))
        for b in (self.add_whisper, self.add_gigaam, self.remove_button,
                  self.up_button, self.down_button):
            buttons.addWidget(b)
        buttons.addStretch()
        info = QLabel("GigaAM: faster, best for pure Russian.\n"
                      "Whisper: slower, handles English/mixed speech.")
        info.setWordWrap(True)
        info.setToolTip(ENGINE_TIPS["whisper"] + "\n\n" + ENGINE_TIPS["gigaam"])
        buttons.addWidget(info)
        layout.addLayout(buttons)

    # ---------------------------------------------------------- model
    def engines(self) -> list:
        return [self.list.item(i).data(Qt.UserRole)
                for i in range(self.list.count())]

    def set_engines(self, names) -> None:
        self.list.clear()
        for name in names:
            if name in ENGINE_LABELS:
                self.add_pass(name)

    def add_pass(self, engine: str) -> None:
        self.list.addItem(ENGINE_LABELS[engine])
        item = self.list.item(self.list.count() - 1)
        item.setData(Qt.UserRole, engine)
        item.setToolTip(ENGINE_TIPS[engine])
        self._renumber()
        self.changed.emit()

    def remove_selected(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)
            self._renumber()
            self.changed.emit()

    def move_selected(self, delta: int) -> None:
        row = self.list.currentRow()
        new = row + delta
        if row < 0 or not (0 <= new < self.list.count()):
            return
        item = self.list.takeItem(row)
        self.list.insertItem(new, item)
        self.list.setCurrentRow(new)
        self._renumber()
        self.changed.emit()

    def _renumber(self) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setText(f"{i + 1}. {ENGINE_LABELS[item.data(Qt.UserRole)]}")
