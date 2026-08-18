"""Word Lists tab: edit the user's lists in-app, save with automatic
tidying (lowercase, ё→е, dedupe, sort — the sortwords behavior), and
test any word/phrase against the CURRENT edits (unsaved included)."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, \
    QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core import config
from ..engine import wordmute as engine
from ..engine.wordlist_tidy import tidy_lines
from ..core.wordlists import explain_matches
from .dialogs import ConfirmDialog
from .i18n import tr

FORMAT_HINT = ("слово = exact ·  корень* = word starts with ·  "
               "*корень* = anywhere in word ·  слово слово = phrase ·  "
               "# comment")


class WordListsTab(QWidget):
    dirtyChanged = Signal(bool)

    def __init__(self, wordlist_paths: dict, settings: dict = None,
                 parent=None):
        super().__init__(parent)
        self._paths = wordlist_paths  # {"russian": Path, "english": Path}
        self._settings = settings if settings is not None else {}
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.list_combo = QComboBox()
        self.list_combo.addItem(tr("Russian list"), "russian")
        self.list_combo.addItem(tr("English list"), "english")
        self.list_combo.currentIndexChanged.connect(self._on_list_switched)
        top.addWidget(self.list_combo)
        self.count_label = QLabel("")
        self.count_label.setObjectName("entries_count")
        top.addWidget(self.count_label)
        top.addStretch()
        self.revert_button = QPushButton(tr("Revert"))
        self.revert_button.clicked.connect(self._load)
        self.save_button = QPushButton(tr("Save (auto-sort)"))
        self.save_button.setProperty("primary", True)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)
        top.addWidget(self.revert_button)
        top.addWidget(self.save_button)
        layout.addLayout(top)

        hint = QLabel(tr(FORMAT_HINT))
        hint.setObjectName("syntax_hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # first-run framing: shipped lists are a template, not policy
        if not self._settings.get("wordlists_note_dismissed"):
            self.template_note = QWidget()
            note_layout = QHBoxLayout(self.template_note)
            note_layout.setContentsMargins(0, 0, 0, 0)
            note_text = QLabel(tr(
                "This is the shipped template — one person's curated "
                "starting point. Edit freely; it's your list."))
            note_text.setProperty("muted", True)
            note_text.setWordWrap(True)
            dismiss = QPushButton("×")
            dismiss.setFlat(True)
            dismiss.setFixedSize(28, 28)
            # the themed QPushButton has 18px side padding: inside a
            # 28px square it eats the glyph and leaves an empty box
            dismiss.setStyleSheet("padding: 0; border: none;")
            dismiss.setToolTip(tr("Hide this note"))
            dismiss.clicked.connect(self._dismiss_note)
            note_layout.addWidget(note_text, stretch=1)
            note_layout.addWidget(dismiss)
            layout.addWidget(self.template_note)
        else:
            self.template_note = None

        self.find_bar = QLineEdit()
        self.find_bar.setPlaceholderText(tr("Find in list… (Enter = next)"))
        self.find_bar.setVisible(False)
        self.find_bar.returnPressed.connect(self._find_next)
        layout.addWidget(self.find_bar)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("wordlist_editor")
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.document().modificationChanged.connect(
            self._on_modified_changed)
        layout.addWidget(self.editor, stretch=3)
        QShortcut(QKeySequence.Find, self, self._toggle_find)

        self._comment_timer = QTimer(self)
        self._comment_timer.setSingleShot(True)
        self._comment_timer.setInterval(400)
        self._comment_timer.timeout.connect(self._highlight_comments)

        self.status_label = QLabel("")
        self.status_label.setProperty("muted", True)
        layout.addWidget(self.status_label)

        tester_box = QGroupBox(tr("Why would this be muted?"))
        tester_layout = QVBoxLayout(tester_box)
        caption = QLabel(tr("Testing your current edits (saved or not) "
                            "plus the other saved list."))
        caption.setProperty("muted", True)
        tester_layout.addWidget(caption)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Word or phrase:")))
        self.tester_input = QLineEdit()
        self.tester_input.textChanged.connect(self._run_tester)
        row.addWidget(self.tester_input, stretch=1)
        tester_layout.addLayout(row)
        self.tester_results = QPlainTextEdit()
        self.tester_results.setObjectName("tester_results")
        self.tester_results.setReadOnly(True)
        self.tester_results.setMaximumHeight(110)
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
        self._highlight_comments()
        self.status_label.setText("")

    def has_unsaved(self) -> bool:
        return self.editor.document().isModified()

    def _on_modified_changed(self, modified: bool):
        self.save_button.setEnabled(modified)
        self.dirtyChanged.emit(modified)

    def _update_count(self):
        lines = self.editor.toPlainText().splitlines()
        n = sum(1 for line in lines
                if line.strip() and not line.strip().startswith("#"))
        self.count_label.setText(tr("{} entries").format(n))

    def _on_text_changed(self):
        if self._loading:
            return
        self._update_count()
        self._comment_timer.start()
        if self.tester_input.text().strip():
            self._run_tester(self.tester_input.text())

    def _highlight_comments(self):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#75798c"))
        selections = []
        doc = self.editor.document()
        block = doc.firstBlock()
        while block.isValid():
            if block.text().lstrip().startswith("#"):
                sel = QTextEdit.ExtraSelection()
                cursor = QTextCursor(block)
                cursor.select(QTextCursor.LineUnderCursor)
                sel.cursor = cursor
                sel.format = fmt
                selections.append(sel)
            block = block.next()
        self.editor.setExtraSelections(selections)

    def _save(self):
        lines = self.editor.toPlainText().splitlines()
        before = len([line for line in lines if line.strip()])
        result = tidy_lines(lines)
        self._path().write_text("\n".join(result) + "\n", encoding="utf-8")
        removed = before - len(result)
        self._load()
        self.status_label.setText(
            tr("Saved: {} entries").format(len(result))
            + (tr(" ({} duplicate(s) merged)").format(removed)
               if removed > 0 else ""))
        self._run_tester(self.tester_input.text())

    def maybe_save(self) -> bool:
        """Offer to save unsaved edits. Returns False if the user
        cancelled the operation that triggered this."""
        if not self.has_unsaved():
            return True
        answer = ConfirmDialog(
            self, title=tr("The word list has unsaved changes."),
            body=tr("Saving also sorts the list and removes duplicates."),
            ok_text=tr("Save"), alt_text=tr("Discard"),
            severity="warn").exec()
        if answer == QDialog.Rejected:      # Cancel
            return False
        if answer == QDialog.Accepted:      # Save
            self._save()
        return True                          # ALT = discard and continue

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

    def _dismiss_note(self):
        if self.template_note is not None:
            self.template_note.setVisible(False)
        self._settings["wordlists_note_dismissed"] = True
        try:
            config.save_settings(self._settings)
        except OSError:
            pass

    # ---------------------------------------------------------- find
    def _toggle_find(self):
        show = not self.find_bar.isVisible()
        self.find_bar.setVisible(show)
        if show:
            self.find_bar.setFocus()
            self.find_bar.selectAll()

    def _find_next(self):
        needle = self.find_bar.text()
        if not needle:
            return
        if not self.editor.find(needle):  # wrap around
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.editor.setTextCursor(cursor)
            self.editor.find(needle)

    # ---------------------------------------------------------- tester
    def _current_wordlist(self):
        """Current editor content (unsaved edits included) merged with
        the OTHER list's saved file — mirrors what a run would use."""
        exact, stems, phrases, subs = engine.parse_wordlist_lines(
            self.editor.toPlainText().splitlines())
        other_key = "english" if self._current_key == "russian" else "russian"
        other = self._paths.get(other_key)
        if other is not None and other.exists():
            e2, st2, ph2, su2 = engine.load_wordlist(other)
            exact |= e2
            stems = stems + st2
            phrases = phrases + ph2
            subs = subs + su2
        return exact, stems, phrases, subs

    def _run_tester(self, text: str):
        text = text.strip()
        if not text:
            self.tester_results.setPlainText("")
            return
        per_word, phrase_hits = explain_matches(text,
                                                self._current_wordlist())
        lines = []
        for word, entries in per_word:
            if entries:
                lines.append(f"{word}  ←  " + ", ".join(entries))
            else:
                lines.append(f"{word}  —  " + tr("(no match)"))
        for ph in phrase_hits:
            lines.append(tr('phrase "{}"  ←  matched').format(ph))
        self.tester_results.setPlainText("\n".join(lines))
