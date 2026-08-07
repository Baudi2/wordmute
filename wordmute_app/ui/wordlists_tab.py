"""Word Lists tab: edit the user's lists in-app, save with automatic
tidying (lowercase, ё→е, dedupe, sort — the sortwords behavior), and
test any word/phrase against the saved list."""

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..engine.wordlist_tidy import tidy_lines
from ..core.wordlists import explain_matches, merge_wordlists
from .i18n import tr

FORMAT_HINT = ("One entry per line:  слово = exact ·  корень* = word starts "
               "with ·  *корень* = anywhere in word ·  слово слово = phrase "
               "·  # comment")


class WordListsTab(QWidget):
    def __init__(self, wordlist_paths: dict, parent=None):
        super().__init__(parent)
        self._paths = wordlist_paths  # {"russian": Path, "english": Path}
        self._loading = False

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.list_combo = QComboBox()
        self.list_combo.addItem(tr("Russian list"), "russian")
        self.list_combo.addItem(tr("English list"), "english")
        self.list_combo.currentIndexChanged.connect(self._on_list_switched)
        top.addWidget(self.list_combo)
        self.count_label = QLabel("")
        top.addWidget(self.count_label)
        top.addStretch()
        self.save_button = QPushButton(tr("Save (auto-sort)"))
        self.save_button.clicked.connect(self._save)
        self.revert_button = QPushButton(tr("Revert"))
        self.revert_button.clicked.connect(self._load)
        top.addWidget(self.save_button)
        top.addWidget(self.revert_button)
        layout.addLayout(top)

        hint = QLabel(FORMAT_HINT)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.editor = QPlainTextEdit()
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor, stretch=3)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        tester_box = QGroupBox(tr("Why would this be muted?"))
        tester_layout = QVBoxLayout(tester_box)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Word or phrase:")))
        self.tester_input = QLineEdit()
        self.tester_input.setPlaceholderText(
            tr("checks the saved lists — save your edits first"))
        self.tester_input.textChanged.connect(self._run_tester)
        row.addWidget(self.tester_input, stretch=1)
        tester_layout.addLayout(row)
        self.tester_results = QPlainTextEdit()
        self.tester_results.setReadOnly(True)
        self.tester_results.setMaximumHeight(120)
        tester_layout.addWidget(self.tester_results)
        layout.addWidget(tester_box, stretch=1)

        self._current_key = "russian"
        self._load()

    # ---------------------------------------------------------- editing
    def _path(self):
        return self._paths[self._current_key]

    def _load(self):
        self._loading = True
        try:
            text = self._path().read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self._loading = False
        self._update_count()
        self.status_label.setText("")

    def has_unsaved(self) -> bool:
        return self.editor.document().isModified()

    def _update_count(self):
        lines = self.editor.toPlainText().splitlines()
        n = sum(1 for line in lines
                if line.strip() and not line.strip().startswith("#"))
        self.count_label.setText(f"{n} entries")

    def _on_text_changed(self):
        if not self._loading:
            self._update_count()

    def _save(self):
        lines = self.editor.toPlainText().splitlines()
        before = len([line for line in lines if line.strip()])
        result = tidy_lines(lines)
        self._path().write_text("\n".join(result) + "\n", encoding="utf-8")
        removed = before - len(result)
        self._load()
        self.status_label.setText(
            f"Saved: {len(result)} entries"
            + (f" ({removed} duplicate(s) merged)" if removed > 0 else ""))
        self._run_tester(self.tester_input.text())

    def maybe_save(self) -> bool:
        """Offer to save unsaved edits. Returns False if the user
        cancelled the operation that triggered this."""
        if not self.has_unsaved():
            return True
        answer = QMessageBox.question(
            self, "WordMute",
            tr("The word list has unsaved changes. Save them?"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            self._save()
        return True

    def _on_list_switched(self):
        new_key = self.list_combo.currentData()
        if new_key == self._current_key:
            return
        if not self.maybe_save():
            # roll the combo back without recursing
            self.list_combo.blockSignals(True)
            self.list_combo.setCurrentIndex(
                self.list_combo.findData(self._current_key))
            self.list_combo.blockSignals(False)
            return
        self._current_key = new_key
        self._load()

    # ---------------------------------------------------------- tester
    def _run_tester(self, text: str):
        text = text.strip()
        if not text:
            self.tester_results.setPlainText("")
            return
        wordlist = merge_wordlists(list(self._paths.values()))
        per_word, phrase_hits = explain_matches(text, wordlist)
        lines = []
        for word, entries in per_word:
            if entries:
                lines.append(f"{word}  ←  " + ", ".join(entries))
            else:
                lines.append(f"{word}  —  (no match)")
        for ph in phrase_hits:
            lines.append(f'phrase "{ph}"  ←  matched')
        self.tester_results.setPlainText("\n".join(lines))
