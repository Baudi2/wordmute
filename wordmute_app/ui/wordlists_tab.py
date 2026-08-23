"""Word Lists tab: edit the user's lists in-app, save with automatic
tidying (lowercase, ё→е, dedupe, sort — the sortwords behavior), find
entries (Ctrl+F bar, design round 4) and test any word/phrase against
the CURRENT edits (unsaved included).

Search ≠ tester: the bar finds entries by substring; the tester at the
bottom answers «will this word be muted?» across every list."""

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, \
    QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core import config
from ..engine import wordmute as engine
from ..engine.wordlist_tidy import tidy_lines
from ..core.wordlists import explain_matches
from .dialogs import ConfirmDialog, repolish
from .elided_label import ElidedLabel
from .i18n import tr, tr_plural
from .theme import FIND_HIGHLIGHT, is_dark, ui_icon

# the legend the «?» popover shows as a two-column grid (design 1f)
SYNTAX_ROWS = (
    ("слово", "exact word"),
    ("корень*", "word starts with"),
    ("*корень*", "anywhere in the word"),
    ("слово слово", "phrase"),
    ("# …", "comment"),
)
# highlighting every «а» of a 4759-line list would build tens of
# thousands of cursors; the count stays exact, the paint is capped
HIGHLIGHT_CAP = 2000
_ACCENT_TEXT = {"dark": "#d2cefd", "light": "#5d5294"}
LIST_NAMES = {"russian": "Russian list", "english": "English list"}


def _fold(text: str) -> str:
    """Search is case-insensitive and ё = е, like every other text
    comparison in the app."""
    return text.lower().replace("ё", "е")


class FindBar(QFrame):
    """The Ctrl+F overlay in the editor's top-right corner (design 1a);
    the «Совпадения» toggle is 1b — the same bar filtering the list."""

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self.setObjectName("wl_find_bar")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(6)
        self.icon = QLabel()
        self.icon.setPixmap(ui_icon("search", 13).pixmap(13, 13))
        row.addWidget(self.icon)
        self.input = QLineEdit()
        self.input.setObjectName("wl_find_input")
        self.input.setPlaceholderText(tr("Find…"))
        row.addWidget(self.input)
        self.count = QLabel("")
        self.count.setObjectName("wl_find_count")
        row.addWidget(self.count)
        sep = QFrame()
        sep.setObjectName("wl_find_sep")
        sep.setFixedSize(1, 16)
        row.addWidget(sep)
        self.prev_btn = self._button("wl_find_prev", "chevron-up",
                                     tr("Previous match (Shift+F3)"))
        self.next_btn = self._button("wl_find_next", "chevron-down",
                                     tr("Next match (F3)"))
        row.addWidget(self.prev_btn)
        row.addWidget(self.next_btn)
        self.filter_btn = QToolButton()
        self.filter_btn.setObjectName("wl_find_filter")
        self.filter_btn.setCheckable(True)
        self.filter_btn.setIcon(ui_icon("funnel", 12))
        self.filter_btn.setText(tr("Matches"))
        self.filter_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.filter_btn.setToolTip(tr("Show only the matching lines"))
        row.addWidget(self.filter_btn)
        self.close_btn = QToolButton()
        self.close_btn.setObjectName("wl_find_close")
        self.close_btn.setText("×")
        self.close_btn.setToolTip(tr("Close (Esc)"))
        row.addWidget(self.close_btn)
        self.hide()

    @staticmethod
    def _button(name: str, icon: str, tip: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName(name)
        button.setIcon(ui_icon(icon, 12))
        button.setToolTip(tip)
        return button

    def reposition(self):
        """Top-right corner of the viewport, inside the editor's frame."""
        editor = self.parentWidget()
        viewport = editor.viewport()
        self.adjustSize()
        corner = viewport.mapTo(editor, QPoint(viewport.width(), 0))
        self.move(corner.x() - self.width() - 16, corner.y() + 8)
        self.raise_()


class WordListsTab(QWidget):
    dirtyChanged = Signal(bool)

    def __init__(self, wordlist_paths: dict, settings: dict = None,
                 parent=None):
        super().__init__(parent)
        self._paths = wordlist_paths  # {"russian": Path, "english": Path}
        self._settings = settings if settings is not None else {}
        self._loading = False
        self._current_key = "russian"   # the ribbon check needs it
        self._comment_selections = []
        self._matches = []
        self._find_current = -1
        self._find_open = False
        # the editor's event filter is live before these exist
        self.find_bar = None
        self.tester_input = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # design 1f: ONE toolbar row instead of three explanatory rows —
        # the syntax legend moves into a popover behind the «?» button;
        # round 4 adds the magnifier that toggles the find bar
        toolbar = QWidget()
        toolbar.setObjectName("wl_toolbar")
        top = QHBoxLayout(toolbar)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.list_combo = QComboBox()
        self.list_combo.setObjectName("wl_list_picker")
        self.list_combo.addItem(tr("Russian list"), "russian")
        self.list_combo.addItem(tr("English list"), "english")
        self.list_combo.currentIndexChanged.connect(self._on_list_switched)
        top.addWidget(self.list_combo)
        self.syntax_help = QToolButton()
        self.syntax_help.setObjectName("wl_syntax_help")
        self.syntax_help.setText("?")
        self.syntax_help.setCheckable(True)
        self.syntax_help.setToolTip(tr("Entry syntax"))
        self.syntax_help.toggled.connect(self._toggle_syntax_popover)
        top.addWidget(self.syntax_help)
        self.search_button = QToolButton()
        self.search_button.setObjectName("wl_search_btn")
        self.search_button.setIcon(ui_icon("search", 13))
        self.search_button.setCheckable(True)
        self.search_button.setToolTip(tr("Find in list (Ctrl+F)"))
        self.search_button.clicked.connect(self._toggle_find)
        top.addWidget(self.search_button)
        self.count_label = QLabel("")
        self.count_label.setObjectName("wl_count")
        top.addWidget(self.count_label)
        top.addStretch()
        self.revert_button = QPushButton(tr("Revert"))
        self.revert_button.clicked.connect(self._load)
        self.save_button = QPushButton(tr("Save"))
        self.save_button.setProperty("primary", True)
        self.save_button.setEnabled(False)
        self.save_button.setToolTip(
            tr("Saving sorts the list, lowercases it and removes "
               "duplicates."))
        self.save_button.clicked.connect(self._save)
        top.addWidget(self.revert_button)
        top.addWidget(self.save_button)
        layout.addWidget(toolbar)
        self._syntax_popover = None
        self._popover_closed_at = 0.0

        # first-run framing: shipped lists are a template, not policy.
        # One 32px line now, dismissed per list (not globally)
        if not self._note_dismissed():
            self.template_note = QFrame()
            self.template_note.setObjectName("wl_template_ribbon")
            note_layout = QHBoxLayout(self.template_note)
            note_layout.setContentsMargins(12, 0, 8, 0)
            note_layout.setSpacing(8)
            note_text = QLabel(tr(
                "This is the shipped template — edit it freely, it's "
                "your list."))
            note_text.setObjectName("wl_template_text")
            note_layout.addWidget(note_text, stretch=1)
            dismiss = QToolButton()
            dismiss.setObjectName("wl_template_dismiss")
            dismiss.setText("×")
            dismiss.setToolTip(tr("Hide this note"))
            dismiss.clicked.connect(self._dismiss_note)
            note_layout.addWidget(dismiss)
            layout.addWidget(self.template_note)
        else:
            self.template_note = None

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("wl_editor")
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.document().modificationChanged.connect(
            self._on_modified_changed)
        self.editor.installEventFilter(self)
        layout.addWidget(self.editor, stretch=3)

        # the find bar floats over the editor; the shortcuts only fire
        # while this tab is the visible one
        self.find_bar = FindBar(self.editor)
        self.find_bar.input.textChanged.connect(
            lambda: self._recompute_find(jump=True))
        self.find_bar.input.installEventFilter(self)
        self.find_bar.prev_btn.clicked.connect(lambda: self._find_step(-1))
        self.find_bar.next_btn.clicked.connect(lambda: self._find_step(1))
        self.find_bar.filter_btn.toggled.connect(self._set_filter)
        self.find_bar.close_btn.clicked.connect(self.close_find)
        QShortcut(QKeySequence.Find, self, self._shortcut_open)
        QShortcut(QKeySequence.FindNext, self,
                  lambda: self._shortcut_step(1))
        QShortcut(QKeySequence.FindPrevious, self,
                  lambda: self._shortcut_step(-1))

        # footer while the filter hides lines
        self.filter_row = QWidget()
        filter_layout = QHBoxLayout(self.filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)
        self.filter_note = ElidedLabel("", tooltip_full=False)
        self.filter_note.setObjectName("wl_filter_note")
        filter_layout.addWidget(self.filter_note, stretch=1)
        show_all = QToolButton()
        show_all.setObjectName("wl_filter_show_all")
        show_all.setText(tr("Show all"))
        show_all.clicked.connect(
            lambda: self.find_bar.filter_btn.setChecked(False))
        filter_layout.addWidget(show_all)
        self.filter_row.hide()
        layout.addWidget(self.filter_row)

        self._comment_timer = QTimer(self)
        self._comment_timer.setSingleShot(True)
        self._comment_timer.setInterval(400)
        self._comment_timer.timeout.connect(self._highlight_comments)

        # «Saved: N entries» after a save; hidden while empty so the
        # tester row sits right under the editor, as in the mock
        self.status_label = QLabel("")
        self.status_label.setProperty("muted", True)
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # the tester is one full-width row: the hint in the placeholder,
        # the verdict + first pattern on the right, the per-list
        # breakdown in the tooltip (design round 4)
        self.tester_row = QFrame()
        self.tester_row.setObjectName("wl_tester_row")
        tester = QHBoxLayout(self.tester_row)
        tester.setContentsMargins(11, 0, 11, 0)
        tester.setSpacing(9)
        self.tester_icon = QLabel()
        tester.addWidget(self.tester_icon)
        self.tester_input = QLineEdit()
        self.tester_input.setObjectName("wl_tester_input")
        self.tester_input.setPlaceholderText(
            tr("Check a word or phrase against this list and the other "
               "saved one…"))
        self.tester_input.textChanged.connect(self._run_tester)
        self.tester_input.installEventFilter(self)
        tester.addWidget(self.tester_input, stretch=1)
        self.tester_result = QLabel("")
        self.tester_result.setObjectName("wl_tester_result")
        tester.addWidget(self.tester_result)
        self.tester_pattern = ElidedLabel("", mode=Qt.ElideLeft,
                                          tooltip_full=False)
        self.tester_pattern.setObjectName("wl_tester_pattern")
        tester.addWidget(self.tester_pattern)
        self.tester_more = QLabel("")
        self.tester_more.setObjectName("wl_tester_more")
        tester.addWidget(self.tester_more)
        layout.addWidget(self.tester_row)
        self._set_tester_state(None)

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
        self._set_status("")
        if self._find_open:
            self._recompute_find()

    def _set_status(self, text: str):
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))

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
        if self._find_open:
            self._recompute_find()
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
        self._comment_selections = selections
        self._apply_extra_selections()

    def _save(self):
        lines = self.editor.toPlainText().splitlines()
        before = len([line for line in lines if line.strip()])
        result = tidy_lines(lines)
        config.write_text_atomic(self._path(), "\n".join(result) + "\n")
        removed = before - len(result)
        self._load()
        self._set_status(
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

    def _note_dismissed(self) -> bool:
        """Per list: dismissing it on the Russian list should not hide
        the framing on the English one (design 1f)."""
        dismissed = self._settings.get("wordlists_note_dismissed")
        if dismissed is True:            # pre-0.6.1: dismissed globally
            return True
        return self._current_key in (dismissed or [])

    def _dismiss_note(self):
        if self.template_note is not None:
            self.template_note.setVisible(False)
        dismissed = self._settings.get("wordlists_note_dismissed")
        dismissed = [] if dismissed is True else list(dismissed or [])
        if self._current_key not in dismissed:
            dismissed.append(self._current_key)
        self._settings["wordlists_note_dismissed"] = dismissed
        try:
            config.save_settings(self._settings)
        except OSError:
            pass

    # ---------------------------------------------------------- find
    def _shortcut_open(self):
        if self.isVisible():
            self.open_find()

    def _shortcut_step(self, delta: int):
        if self.isVisible() and self._find_open:
            self._find_step(delta)

    def _toggle_find(self, checked: bool):
        if checked:
            self.open_find()
        else:
            self.close_find()

    def open_find(self):
        """Ctrl+F / the magnifier: a single-line selection prefills the
        field; when already open, Ctrl+F just refocuses it."""
        selected = self.editor.textCursor().selectedText()
        if selected and " " not in selected:
            self.find_bar.input.setText(selected)
        self._find_open = True
        self.find_bar.show()
        self.find_bar.reposition()
        self.find_bar.input.setFocus()
        self.find_bar.input.selectAll()
        self.search_button.blockSignals(True)
        self.search_button.setChecked(True)
        self.search_button.blockSignals(False)
        self._recompute_find(jump=True)

    def close_find(self):
        """Esc / ×: highlights off, filter off, focus back to the list."""
        if self.find_bar.filter_btn.isChecked():
            self.find_bar.filter_btn.setChecked(False)   # restores lines
        self._find_open = False
        self.find_bar.hide()
        self._matches = []
        self._find_current = -1
        self._apply_extra_selections()
        self.find_bar.count.setText("")
        self.search_button.blockSignals(True)
        self.search_button.setChecked(False)
        self.search_button.blockSignals(False)
        self.editor.setFocus()

    def _recompute_find(self, jump: bool = False):
        """Substring, case-insensitive, ё = е; no regex. str.find over
        4759 lines is instant — no debounce. `jump` scrolls the first
        match into view — for typing in the bar, never for edits in
        the editor (that would hijack the caret)."""
        needle = _fold(self.find_bar.input.text())
        self._matches = []
        if needle and self._find_open:
            haystack = _fold(self.editor.toPlainText())
            i = haystack.find(needle)
            while i >= 0:
                self._matches.append(i)
                i = haystack.find(needle, i + 1)
        self._find_current = 0 if self._matches else -1
        if jump and self._matches:
            self._goto_current()
        self._apply_extra_selections()
        self._update_find_count()
        if self.find_bar.filter_btn.isChecked():
            self._apply_filter()

    def _goto_current(self):
        cursor = self.editor.textCursor()
        cursor.setPosition(self._matches[self._find_current])
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()

    def _find_step(self, delta: int):
        if not self._matches:
            return
        self._find_current = (self._find_current + delta) % len(self._matches)
        self._goto_current()
        self._apply_extra_selections()
        self._update_find_count()

    def _update_find_count(self):
        bar = self.find_bar
        if bar.filter_btn.isChecked() and bar.input.text():
            return                      # the filter shows «N lines»
        if not bar.input.text():
            bar.count.setText("")
            bar.count.setToolTip("")
        elif self._matches:
            bar.count.setText(tr("{} of {}").format(
                self._find_current + 1, len(self._matches)))
            bar.count.setToolTip("")
        else:
            bar.count.setText(tr("no matches"))
            bar.count.setToolTip(tr(
                "Search finds list entries. To check whether a word gets "
                "muted, use the tester below."))

    def _apply_extra_selections(self):
        """Comment dimming + search highlights share one list — setting
        either alone would wipe the other."""
        selections = list(self._comment_selections)
        if self._matches:
            match_bg, cur_bg, cur_fg = FIND_HIGHLIGHT[
                "dark" if is_dark() else "light"]
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(match_bg))
            cur_fmt = QTextCharFormat()
            cur_fmt.setBackground(QColor(cur_bg))
            cur_fmt.setForeground(QColor(cur_fg))
            length = len(self.find_bar.input.text())
            doc = self.editor.document()
            shown = list(enumerate(self._matches[:HIGHLIGHT_CAP]))
            if self._find_current >= HIGHLIGHT_CAP:
                shown.append((self._find_current,
                              self._matches[self._find_current]))
            for index, pos in shown:
                sel = QTextEdit.ExtraSelection()
                cursor = QTextCursor(doc)
                cursor.setPosition(pos)
                cursor.setPosition(pos + length, QTextCursor.KeepAnchor)
                sel.cursor = cursor
                sel.format = cur_fmt if index == self._find_current else fmt
                selections.append(sel)
        self.editor.setExtraSelections(selections)

    # ---------------------------------------------------------- filter
    def _set_filter(self, on: bool):
        if on:
            self._apply_filter()
        else:
            self._clear_filter()

    def _apply_filter(self):
        """Only the matching lines stay visible; editing with the
        context hidden is dangerous, so the editor goes read-only. An
        empty query hides nothing (and the footer stays away)."""
        needle = _fold(self.find_bar.input.text())
        doc = self.editor.document()
        shown = 0
        block = doc.firstBlock()
        while block.isValid():
            visible = not needle or needle in _fold(block.text())
            block.setVisible(visible)
            shown += visible
            block = block.next()
        doc.markContentsDirty(0, doc.characterCount())
        self.editor.viewport().update()
        active = bool(needle)
        self.editor.setReadOnly(active)
        self.find_bar.prev_btn.setEnabled(not active)
        self.find_bar.next_btn.setEnabled(not active)
        self.filter_row.setVisible(active)
        if active:
            # lines, not blocks: the trailing newline's empty block
            # made the footer say 4560 under a toolbar saying 4559
            total = len(self.editor.toPlainText().splitlines())
            self.filter_note.setText(
                tr("showing {} of {} — filter by «{}» · editing off")
                .format(shown, total, self.find_bar.input.text()))
            self.find_bar.count.setText(tr_plural("{} lines", shown))
            self.find_bar.count.setToolTip("")
        else:
            self._update_find_count()

    def _clear_filter(self):
        doc = self.editor.document()
        block = doc.firstBlock()
        while block.isValid():
            block.setVisible(True)
            block = block.next()
        doc.markContentsDirty(0, doc.characterCount())
        self.editor.viewport().update()
        self.editor.setReadOnly(False)
        self.find_bar.prev_btn.setEnabled(True)
        self.find_bar.next_btn.setEnabled(True)
        self.filter_row.setVisible(False)
        self._update_find_count()

    # ---------------------------------------------------------- tester
    def _list_wordlist(self, key: str):
        """The current list = the editor (unsaved edits included); the
        other one = its saved file — mirrors what a run would use."""
        if key == self._current_key:
            return engine.parse_wordlist_lines(
                self.editor.toPlainText().splitlines())
        path = self._paths.get(key)
        if path is not None and path.exists():
            return engine.load_wordlist(path)
        return None

    def _set_tester_state(self, state):
        self.tester_row.setProperty("state", state)
        self.tester_result.setProperty("state", state)
        repolish(self.tester_row)
        repolish(self.tester_result)
        tint = (_ACCENT_TEXT["dark" if is_dark() else "light"]
                if state == "hit" else None)
        self.tester_icon.setPixmap(
            ui_icon("check-circle", 13, tint).pixmap(13, 13))

    def _set_tester_tooltip(self, text: str):
        for widget in (self.tester_row, self.tester_input,
                       self.tester_result, self.tester_pattern,
                       self.tester_more):
            widget.setToolTip(text)

    def _run_tester(self, text: str):
        text = text.strip()
        if not text:
            self.tester_result.setText("")
            self.tester_pattern.setText("")
            self.tester_more.setText("")
            self._set_tester_tooltip("")
            self._set_tester_state(None)
            return
        # the verdict comes from the first hit — the current list first;
        # every other list with a hit is counted, the breakdown per list
        # goes into the tooltip
        keys = [self._current_key] + [k for k in self._paths
                                      if k != self._current_key]
        pattern, lists_hit, tooltip = "", 0, []
        for key in keys:
            wordlist = self._list_wordlist(key)
            name = tr(LIST_NAMES.get(key, key))
            if wordlist is None:
                continue
            per_word, phrase_hits = explain_matches(text, wordlist)
            lines = []
            first = ""
            for word, entries in per_word:
                if entries:
                    first = first or entries[0]
                    lines.append(f"  {word}  ←  " + ", ".join(entries))
                else:
                    lines.append(f"  {word}  —  " + tr("(no match)"))
            for phrase in phrase_hits:
                first = first or phrase
                lines.append("  " + tr('phrase "{}"  ←  matched')
                             .format(phrase))
            if first:
                lists_hit += 1
                pattern = pattern or first
                tooltip.append(name + ":")
                tooltip.extend(lines)
            else:
                tooltip.append(f"{name}: {tr('no matches')}")
        if pattern:
            self.tester_result.setText(tr("will be muted") + " ←")
            self.tester_pattern.setText(pattern)
            others = lists_hit - 1
            self.tester_more.setText(
                tr_plural("· also in {} lists", others) if others else "")
            self._set_tester_state("hit")
        else:
            self.tester_result.setText(tr("will not be muted — no matches"))
            self.tester_pattern.setText("")
            self.tester_more.setText("")
            self._set_tester_state(None)
        self._set_tester_tooltip("\n".join(tooltip))

    # ------------------------------------------------------ syntax help
    def _toggle_syntax_popover(self, show: bool):
        """A Popup QFrame, not a QMenu: the legend is a two-column grid,
        which a menu cannot lay out.

        The reopen guard: clicking the checked button closes the popup
        BEFORE the click lands (Qt.Popup eats the press), the Hide
        filter unchecks the button, and the same click then re-checks
        it — without the timestamp the button could only ever open."""
        import time
        if show and time.monotonic() - self._popover_closed_at < 0.25:
            self.syntax_help.setChecked(False)
            return
        if not show:
            if self._syntax_popover is not None:
                self._syntax_popover.hide()
            return
        if self._syntax_popover is None:
            self._syntax_popover = self._build_syntax_popover()
        popover = self._syntax_popover
        popover.adjustSize()
        below = self.syntax_help.mapToGlobal(
            self.syntax_help.rect().bottomLeft())
        popover.move(below.x(), below.y() + 6)
        popover.show()

    def _build_syntax_popover(self) -> QFrame:
        popover = QFrame(self, Qt.Popup)
        popover.setObjectName("wl_syntax_popover")
        grid = QGridLayout(popover)
        grid.setContentsMargins(14, 12, 16, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        caption = QLabel(tr("ENTRY SYNTAX"))
        caption.setObjectName("wl_syntax_caption")
        grid.addWidget(caption, 0, 0, 1, 2)
        for row, (token, desc) in enumerate(SYNTAX_ROWS, start=1):
            token_label = QLabel(token)
            token_label.setProperty("syntaxToken", True)
            desc_label = QLabel(tr(desc))
            desc_label.setProperty("syntaxDesc", True)
            grid.addWidget(token_label, row, 0)
            grid.addWidget(desc_label, row, 1)
        popover.installEventFilter(self)
        return popover

    # ---------------------------------------------------------- events
    def eventFilter(self, obj, event):
        kind = event.type()
        if obj is self._syntax_popover and kind == QEvent.Hide:
            import time
            self._popover_closed_at = time.monotonic()
            self.syntax_help.setChecked(False)
        elif (self.find_bar is not None and obj is self.find_bar.input
              and kind == QEvent.KeyPress):
            key = event.key()
            if key == Qt.Key_Escape:
                self.close_find()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                backwards = bool(event.modifiers() & Qt.ShiftModifier)
                self._find_step(-1 if backwards else 1)
                return True
        elif obj is self.editor:
            if kind == QEvent.Resize and self._find_open:
                self.find_bar.reposition()
            elif (kind == QEvent.KeyPress and self._find_open
                  and event.key() == Qt.Key_Escape):
                self.close_find()
                return True
        elif obj is self.tester_input and kind in (QEvent.FocusIn,
                                                    QEvent.FocusOut):
            # the input is borderless inside the row: the row shows
            # the focus ring instead
            self.tester_row.setProperty("focused", kind == QEvent.FocusIn)
            repolish(self.tester_row)
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        # theme-dependent paints (highlight colors, icon tint) follow a
        # live theme switch the next time the tab is shown
        self._apply_extra_selections()
        self._set_tester_state(self.tester_row.property("state"))
        if self._find_open:
            self.find_bar.reposition()
