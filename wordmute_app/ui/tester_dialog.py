"""'Why was this muted?' tester: type a word or phrase, see which
word-list entries would catch it — live, using the currently selected
lists."""

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core.wordlists import explain_matches, merge_wordlists
from .i18n import tr


class TesterDialog(QDialog):
    def __init__(self, wordlist_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Word Tester…").rstrip("…"))
        self.resize(520, 420)
        self._wordlist = merge_wordlists(wordlist_paths)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Word or phrase:")))
        self.input = QLineEdit()
        self.input.textChanged.connect(self._update)
        row.addWidget(self.input, stretch=1)
        layout.addLayout(row)

        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        layout.addWidget(self.results, stretch=1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        close_row.addWidget(close)
        layout.addLayout(close_row)

    def _update(self, text: str):
        text = text.strip()
        if not text:
            self.results.setPlainText("")
            return
        per_word, phrase_hits = explain_matches(text, self._wordlist)
        lines = []
        for word, entries in per_word:
            if entries:
                lines.append(f"{word}  ←  " + ", ".join(entries))
            else:
                lines.append(f"{word}  —  (no match)")
        for ph in phrase_hits:
            lines.append(f'phrase "{ph}"  ←  matched')
        self.results.setPlainText("\n".join(lines))
