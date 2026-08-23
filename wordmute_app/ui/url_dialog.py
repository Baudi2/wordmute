"""Add-URL dialog: paste a link, optionally fetch yt-dlp's format list
and pick a specific quality, or add straight away at best quality.
Pasting SEVERAL links at once switches to batch mode: all of them are
added at best quality in one go."""

import re

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core import downloader
from ..core.jobs import QueueItem
from .flow_layout import FlowLayout, make_chip
from .hover_table import HoverRowTable
from .i18n import tr, tr_plural
from .threads import detach_thread, start_thread

# keep fetch threads alive if their dialog closes early; Qt drops the
# signal connections with the dialog, so late emits are harmless
_live_workers = set()

# batch mode holds this many links without scrolling; the box opens at
# this full height right away (tester: growth under the paste felt
# broken, and 3 visible links was far too tight)
MAX_LINES = 10
CHIP_ACCENT = "#9184d9"
CHIP_WARN = "#cdb380"

# a URL runs until whitespace/comma/semicolon OR the next http(s)://
# — QLineEdit may join pasted lines with nothing in between
_URL_RE = re.compile(r"https?://(?:(?!https?://)[^\s,;])+")


def extract_urls(text: str) -> list:
    """Every distinct http(s) link in the text, in order."""
    seen = []
    for url in _URL_RE.findall(text or ""):
        if url not in seen:
            seen.append(url)
    return seen


class _UrlEdit(QPlainTextEdit):
    """URL input that grows: one line for a single link, a proper
    multi-line list when several are pasted.

    Enter: submits in single mode (the old one-line behavior), inserts
    a NEWLINE in batch mode — swallowing it there made hand-typing a
    link into an existing list impossible. Shift+Enter always inserts.
    Pastes land on their own line: dropping a URL with the caret at the
    end of an existing link used to glue them together."""
    submitted = Signal()
    allow_newline = False

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and not (event.modifiers() & Qt.ShiftModifier)
                and not self.allow_newline):
            self.submitted.emit()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        urls = extract_urls(source.text() if source.hasText() else "")
        if not urls:
            super().insertFromMimeData(source)
            return
        cursor = self.textCursor()
        prefix = ("\n" if cursor.block().text()[:cursor.positionInBlock()]
                  .strip() else "")
        cursor.insertText(prefix + "\n".join(urls))


class FormatListWorker(QThread):
    ready = Signal(dict)
    error = Signal(str)

    def __init__(self, url: str, cookies=None):
        super().__init__()
        self._url = url
        self._cookies = cookies
        _live_workers.add(self)
        self.finished.connect(lambda: _live_workers.discard(self))

    def run(self):
        try:
            self.ready.emit(
                downloader.list_formats(self._url, cookies=self._cookies))
        except Exception as exc:
            self.error.emit(str(exc))


class AddUrlDialog(QDialog):
    COLUMNS = ["Quality", "Size", "Note", "Ext", "FPS", "Type"]

    def __init__(self, parent=None, url: str = "", cookies=None,
                 auto_fetch: bool = True, quality: str = None):
        super().__init__(parent)
        self.setObjectName("add_url_dialog")
        self.setWindowTitle(tr("Add URL"))
        # single mode needs room for the format table; batch mode sizes
        # itself to its content and restores this on the way back
        self._single_size = QSize(780, 640)
        self.resize(self._single_size)
        self.setMinimumWidth(720)
        self._info = None
        self._use_best = False
        self._cookies = cookies
        self._auto_fetch = auto_fetch
        self._fetch_generation = 0
        self._fetchers = []           # format fetches still running
        self._multi_urls = []

        self._reformatting = False   # guard: setPlainText re-enters

        layout = QVBoxLayout(self)
        self.url_edit = _UrlEdit()
        self.url_edit.setObjectName("url_input")
        self.url_edit.setPlainText(url)
        self.url_edit.setPlaceholderText("https://…")
        self.url_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.url_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._single_lines = 2      # a link plus room to paste another
        # formats load automatically: debounce typing, Enter = right now
        self._fetch_timer = QTimer(self)
        self._fetch_timer.setSingleShot(True)
        self._fetch_timer.setInterval(800)
        self._fetch_timer.timeout.connect(self._fetch)
        self.url_edit.textChanged.connect(self._schedule_fetch)
        self.url_edit.submitted.connect(self._fetch)
        layout.addWidget(self.url_edit)

        self.status = QLabel(tr("Paste a video URL — the format list "
                                "loads automatically."))
        self.status.setWordWrap(True)
        self.status.setProperty("muted", True)
        layout.addWidget(self.status)

        # one chip per host, so four links read as four links without
        # scanning the text; a warn chip counts lines that are not URLs
        self.chips_row = QWidget()
        self.chips_row.setObjectName("url_chips_row")
        # wrapping, not squeezing: five hosts plus the warning used to
        # clip the last chip mid-word
        self._chips_layout = FlowLayout(self.chips_row)
        self.chips_row.setVisible(False)
        layout.addWidget(self.chips_row)

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)  # indeterminate
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setVisible(False)
        layout.addWidget(self.loading_bar)

        # batch mode has no per-link format table — one quality cap for
        # the whole batch instead of silently grabbing 4K
        self.quality_row = QWidget()
        self.quality_row.setObjectName("url_options_row")
        quality_layout = QHBoxLayout(self.quality_row)
        quality_layout.setContentsMargins(0, 0, 0, 0)
        quality_layout.setSpacing(8)
        quality_label = QLabel(tr("Quality for all links:"))
        quality_label.setObjectName("url_quality_label")
        quality_layout.addWidget(quality_label)
        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("url_quality")
        for key, label, _spec in downloader.QUALITY_PRESETS:
            self.quality_combo.addItem(tr(label), key)
        preset = (quality if quality in
                  [k for k, _, _ in downloader.QUALITY_PRESETS]
                  else downloader.DEFAULT_QUALITY)
        self.quality_combo.setCurrentIndex(
            self.quality_combo.findData(preset))
        self.quality_combo.currentIndexChanged.connect(
            lambda _: self._update_multi_labels())
        quality_layout.addWidget(self.quality_combo)
        quality_layout.addStretch()
        self.quality_row.setVisible(False)
        layout.addWidget(self.quality_row)

        if not self._cookies:
            cookies_row = QHBoxLayout()
            self.cookies_hint = QLabel(tr(
                "Members-only sites (e.g. Boosty) may need your cookies "
                "file —"))
            self.cookies_hint.setObjectName("url_cookies_hint")
            self.cookies_hint.setProperty("muted", True)
            cookies_link = QToolButton()
            cookies_link.setObjectName("url_cookies_link")
            cookies_link.setText(tr("set it in Settings"))
            cookies_link.clicked.connect(self._goto_settings)
            cookies_row.addWidget(self.cookies_hint)
            cookies_row.addWidget(cookies_link)
            cookies_row.addStretch()
            layout.addLayout(cookies_row)

        # design 2b: the format list lives in one frame with a darker
        # "tail" AFTER the last row and a pinned «Selected: …» bar. The
        # table and the tail scroll together inside one scroll area —
        # a pinned tail read as "stuck to the window" on long lists,
        # where it belongs after format #24, not under format #10
        self.format_area = QFrame()
        self.format_area.setObjectName("format_area")
        area_box = QVBoxLayout(self.format_area)
        area_box.setContentsMargins(0, 0, 0, 0)
        area_box.setSpacing(0)
        self.table = HoverRowTable(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [tr(c) for c in self.COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(lambda _: self.accept())
        self.table.itemSelectionChanged.connect(self._on_selection)
        # the OUTER area scrolls; the table itself never does (it is
        # sized to its full content once formats arrive). The table
        # still swallows wheel events even with nothing to scroll, so
        # they are forwarded (eventFilter below) or the list would
        # freeze under the cursor
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.viewport().installEventFilter(self)
        from PySide6.QtWidgets import QScrollArea
        self.format_scroll = QScrollArea()
        self.format_scroll.setObjectName("format_scroll")
        self.format_scroll.setWidgetResizable(True)
        self.format_scroll.setFrameShape(QFrame.NoFrame)
        scroll_body = QWidget()
        scroll_box = QVBoxLayout(scroll_body)
        scroll_box.setContentsMargins(0, 0, 0, 0)
        scroll_box.setSpacing(0)
        # pre-fetch the (empty, hint-sized) table stretches to fill;
        # once its height is fixed to the content, the visible tail
        # takes any leftover instead (the short-list deep look)
        scroll_box.addWidget(self.table, stretch=1)

        self.format_tail = QWidget()
        self.format_tail.setObjectName("format_tail")
        tail_box = QVBoxLayout(self.format_tail)
        tail_box.setContentsMargins(16, 8, 16, 8)
        tail_box.setSpacing(4)
        tail_box.addStretch()
        end_line = QFrame()
        end_line.setObjectName("format_end_line")
        end_line.setFixedHeight(1)
        tail_box.addWidget(end_line)
        self.tail_title = QLabel("")
        self.tail_title.setObjectName("format_tail_title")
        self.tail_title.setAlignment(Qt.AlignCenter)
        tail_box.addWidget(self.tail_title)
        self.tail_hint = QLabel(
            tr("Need another option? A cookies file sometimes helps"))
        self.tail_hint.setObjectName("format_tail_hint")
        self.tail_hint.setAlignment(Qt.AlignCenter)
        tail_box.addWidget(self.tail_hint)
        tail_box.addStretch()
        # roomy even on long lists, where it sits right after the rows
        self.format_tail.setMinimumHeight(96)
        scroll_box.addWidget(self.format_tail, stretch=1)
        self.format_scroll.setWidget(scroll_body)
        area_box.addWidget(self.format_scroll, stretch=1)

        self.selected_bar = QWidget()
        self.selected_bar.setObjectName("format_selected")
        bar_box = QHBoxLayout(self.selected_bar)
        bar_box.setContentsMargins(16, 9, 16, 9)
        self.selected_label = QLabel("")
        self.selected_label.setObjectName("format_selected_label")
        bar_box.addWidget(self.selected_label, stretch=1)
        self.selected_detail = QLabel("")
        self.selected_detail.setObjectName("format_selected_detail")
        bar_box.addWidget(self.selected_detail)
        self.selected_bar.setVisible(False)
        area_box.addWidget(self.selected_bar)

        # size the input once the sheet is applied: before that the mono
        # face is not in place and the box comes out a third too short
        QTimer.singleShot(0, self._apply_single_geometry)
        layout.addWidget(self.format_area, stretch=1)

        self.format_tail.setVisible(False)

        footer = QWidget()
        footer.setObjectName("add_url_footer")
        self._footer_layout = buttons_row = QHBoxLayout(footer)
        buttons_row.setContentsMargins(0, 8, 0, 0)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("add_url_summary")
        self.summary_label.setVisible(False)
        buttons_row.addWidget(self.summary_label)
        self.best_button = QPushButton(tr("Add (best quality)"))
        self.best_button.setObjectName("btn_add_urls")
        self.best_button.setProperty("primary", True)
        self.best_button.setToolTip(
            tr("Skip the format list and download best video+audio."))
        self.best_button.clicked.connect(self._accept_best)
        buttons_row.addWidget(self.best_button)
        buttons_row.addStretch()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(tr("Add selected"))
        self.buttons.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        buttons_row.addWidget(self.buttons)
        layout.addWidget(footer)
        self._update_ok()
        if auto_fetch and self._looks_like_url(url):
            QTimer.singleShot(0, self._fetch)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.table.viewport() and event.type() == QEvent.Wheel:
            bar = self.format_scroll.verticalScrollBar()
            delta = event.pixelDelta().y() or event.angleDelta().y() // 2
            bar.setValue(bar.value() - delta)
            return True
        return super().eventFilter(obj, event)

    def _goto_settings(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, "tabs") \
                and hasattr(parent, "settings_tab"):
            parent.tabs.setCurrentWidget(parent.settings_tab)
        self.reject()

    # ---------------------------------------------------------- fetching
    def _url(self) -> str:
        return self.url_edit.toPlainText().strip()

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        return text.strip().startswith(("http://", "https://"))

    def _schedule_fetch(self):
        if self._reformatting:
            return
        urls = extract_urls(self.url_edit.toPlainText())
        if len(urls) >= 2:
            self._enter_multi_mode(urls)
            return
        if self._multi_urls:
            self._leave_multi_mode()
        if self._looks_like_url(self._url()):
            self._fetch_timer.start()
        else:
            self._fetch_timer.stop()

    def _enter_multi_mode(self, urls):
        """Several links pasted: no per-link format table — one quality
        cap applies to the whole batch, and the input takes over the
        table's space to show one link per line."""
        self._fetch_timer.stop()
        first_time = not self._multi_urls
        self._multi_urls = urls
        self.loading_bar.setVisible(False)
        self.table.setRowCount(0)
        self.format_area.setVisible(False)   # useless without a fetch
        self._info = None
        self.quality_row.setVisible(True)
        self._normalize_text()
        self.url_edit.allow_newline = True   # Enter = another link
        if first_time:
            self._url_stretch(True)
            # nothing to select without the table
            self.buttons.button(QDialogButtonBox.Ok).setVisible(False)
            # design: [summary] … [Отмена] [Добавить N] — the primary
            # moves to the right of Cancel for the batch
            self._footer_layout.removeWidget(self.best_button)
            self._footer_layout.addWidget(self.best_button)
            self._resize_input()
        self._update_multi_labels()
        self._update_ok()

    def _normalize_text(self):
        """Split a paste that joined several links onto one line, drop
        blank lines — and touch NOTHING else.

        The old version rewrote the box to «the URLs we found», which
        deleted every half-typed link the moment its first letter was
        not yet a URL, and pushed the caret to the end after each paste.
        Editing by hand has to survive this."""
        text = self.url_edit.toPlainText()
        cursor = self.url_edit.textCursor()
        caret_block = cursor.blockNumber()
        caret_column = cursor.positionInBlock()
        # split("\n"), NOT splitlines(): the latter drops the trailing
        # empty line, which is exactly the one the user just made by
        # pressing Enter to type another link
        source = text.split("\n")
        lines, target_block = [], caret_block
        for index, line in enumerate(source):
            found = extract_urls(line)
            if len(found) > 1:               # one paste, several links
                if index < caret_block:
                    target_block += len(found) - 1
                lines.extend(found)
            elif line.strip():
                lines.append(line.strip())
            elif index == caret_block and index == len(source) - 1:
                # the empty line being typed on stays; stray blank lines
                # anywhere else (a paste artifact) go
                lines.append("")
            elif index < caret_block:
                target_block -= 1
        wanted = "\n".join(lines)
        if wanted == text:
            return
        self._reformatting = True
        try:
            self.url_edit.setPlainText(wanted)
            cursor = self.url_edit.textCursor()
            block = cursor.document().findBlockByNumber(
                min(max(target_block, 0), max(len(lines) - 1, 0)))
            cursor.setPosition(block.position()
                               + min(caret_column, block.length() - 1))
            self.url_edit.setTextCursor(cursor)
        finally:
            self._reformatting = False

    def _url_stretch(self, on: bool):
        """Batch mode sizes the input to its content instead of eating
        the whole dialog (design 1c) — the quality row and the button
        stay within reach of the eye."""
        layout = self.layout()
        layout.setStretchFactor(self.url_edit, 0)
        if on:
            self._resize_input()

    def _line_height(self) -> float:
        """The painted line box of the sheet's mono face — QFontMetrics
        of the widget font and the document layout (which measures in
        LINES, not pixels) both under-report it."""
        self.url_edit.ensurePolished()
        return (self.url_edit.cursorRect().height()
                or QFontMetrics(self.url_edit.font()).lineSpacing()) + 2

    def _set_input_lines(self, lines: int):
        """Size the box to hold `lines` links without scrolling, never
        below what the stylesheet asks for (its min-height used to win
        over a smaller fixed height and the status line was painted on
        top of the input's own border)."""
        edit = self.url_edit
        chrome = max(edit.height() - edit.viewport().height(), 4)
        # +6: with exactly lines*line the viewport clips the last line
        # by a hair and QPlainTextEdit starts scrolling
        wanted = int(lines * self._line_height()) + chrome + 6
        edit.setMinimumHeight(0)
        edit.setMaximumHeight(16777215)
        edit.setFixedHeight(max(wanted, edit.minimumSizeHint().height()))

    def _apply_single_geometry(self):
        """Single mode keeps a roomy window: the format table needs the
        space, and after a batch the dialog must not stay the compact
        stub batch mode shrank it to."""
        if self._multi_urls:
            return
        self._set_input_lines(self._single_lines)
        self.resize(self._single_size)

    def _resize_input(self):
        """Batch mode: the box holds MAX_LINES links from the start —
        a constant, roomy height (per tester feedback) instead of
        growing under the user's paste; past MAX_LINES it scrolls."""
        self._set_input_lines(MAX_LINES)
        self.adjustSize()

    def _host_counts(self):
        """[(host, count), …] in first-seen order, plus the number of
        non-empty lines that are not links at all."""
        from urllib.parse import urlparse
        hosts, bad = {}, 0
        for line in self.url_edit.toPlainText().splitlines():
            line = line.strip()
            if not line:
                continue
            if not self._looks_like_url(line):
                bad += 1
                continue
            host = urlparse(line).netloc.removeprefix("www.")
            hosts[host] = hosts.get(host, 0) + 1
        return list(hosts.items()), bad

    def _rebuild_chips(self):
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        hosts, bad = self._host_counts()
        for host, count in hosts:
            self._chips_layout.addWidget(
                make_chip(f"{host} · {count}", CHIP_ACCENT))
        if bad:
            self._chips_layout.addWidget(make_chip(
                tr_plural("{} lines are not links", bad),
                CHIP_WARN, warn=True))
        self.chips_row.setVisible(bool(hosts))
        self.chips_row.updateGeometry()

    def _update_multi_labels(self):
        if not self._multi_urls:
            return
        _spec, label = downloader.quality_spec(self.quality())
        count = len(self._multi_urls)
        self.status.setVisible(False)
        self.summary_label.setVisible(True)
        self.summary_label.setText(
            f"{tr_plural('{} links', count)} · {tr(label)}")
        self.best_button.setText(tr("Add {} to the queue").format(count))
        self._rebuild_chips()

    def quality(self) -> str:
        return self.quality_combo.currentData()

    def _leave_multi_mode(self):
        self._multi_urls = []
        self.url_edit.allow_newline = False
        self.quality_row.setVisible(False)
        self.chips_row.setVisible(False)
        self.summary_label.setVisible(False)
        self.format_area.setVisible(True)
        self.buttons.button(QDialogButtonBox.Ok).setVisible(True)
        # the primary returns to the footer's left edge (single design)
        self._footer_layout.removeWidget(self.best_button)
        self._footer_layout.insertWidget(1, self.best_button)
        self._url_stretch(False)
        self._apply_single_geometry()       # not the batch-sized stub
        self.best_button.setText(tr("Add (best quality)"))
        self.status.setVisible(True)
        self.status.setText(tr("Paste a video URL — the format list "
                               "loads automatically."))

    def _fetch(self):
        # auto_fetch=False (tests): the debounce still arms, but no
        # yt-dlp call ever leaves — a fetch left running against a fake
        # URL aborted the test session at exit
        if self._multi_urls or not self._auto_fetch:
            return
        url = self._url()
        if not self._looks_like_url(url):
            return
        self._fetch_timer.stop()
        self._fetch_generation += 1
        generation = self._fetch_generation
        self.status.setText(tr("Fetching format list…"))
        self.loading_bar.setVisible(True)
        self.table.setRowCount(0)
        self.table.setMinimumHeight(0)
        self.table.setMaximumHeight(16777215)
        self.format_tail.setVisible(False)
        self.selected_bar.setVisible(False)
        self._info = None
        self._update_ok()
        worker = FormatListWorker(url, cookies=self._cookies)
        # a newer fetch (edited URL) makes this one's result stale
        worker.ready.connect(
            lambda info, g=generation:
            self._on_formats_ready(info)
            if g == self._fetch_generation else None)
        worker.error.connect(
            lambda message, g=generation:
            self._on_fetch_error(message)
            if g == self._fetch_generation else None)
        self._fetchers.append(worker)
        worker.finished.connect(
            lambda w=worker: self._fetchers.remove(w)
            if w in self._fetchers else None)
        start_thread(self, worker)

    def done(self, result: int):
        """accept(), reject() (Esc / Cancel) and the close box all end
        here. A format fetch still running (yt-dlp has no cancel) must
        not die with the dialog — Qt aborts the process when a running
        QThread is destroyed; it finishes detached, its result is
        stale by generation."""
        self._fetch_generation += 1
        for worker in list(self._fetchers):
            detach_thread(worker)
        self._fetchers.clear()
        super().done(result)

    def _on_formats_ready(self, info: dict):
        self._info = info
        self.loading_bar.setVisible(False)
        duration = info.get("duration")
        if duration and duration >= 60:
            extra = f" · {int(duration // 60)} {tr('min')}"
        elif duration:
            extra = f" · {int(duration)} {tr('s')}"
        else:
            extra = ""
        self.status.setText(f"{info['title']}{extra}")
        self.table.setRowCount(0)
        self._add_row([tr("Best video+audio\n(recommended)"),
                       "", "", "", "", ""], None)
        self.table.setRowHeight(0, 56)
        for f in info["formats"]:
            d = downloader.describe_format(f, duration=duration)
            self._add_row(
                [d["resolution"] or d["id"], d["size"], d["note"],
                 d["ext"], str(int(d["fps"])) if d["fps"] else "",
                 tr(d["kind"])],
                f)
        # number only the real formats: with the «best» row counted,
        # the last row read 25 against the tail's «— 24»
        self.table.setVerticalHeaderLabels(
            [""] + [str(i) for i in range(1, self.table.rowCount())])
        self.table.selectRow(0)
        header_h = self.table.horizontalHeader().height()
        content = header_h + 2 * self.table.frameWidth() + sum(
            self.table.rowHeight(r) for r in range(self.table.rowCount()))
        self.table.setFixedHeight(content)   # the OUTER area scrolls
        self.tail_title.setText(
            tr("That's every format this site offered — {}")
            .format(len(info["formats"])))
        self.format_tail.setVisible(True)
        self._update_ok()

    def _add_row(self, texts, fmt):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, text in enumerate(texts):
            item = QTableWidgetItem(text)
            if col == 0:
                item.setData(Qt.UserRole, fmt)
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item)

    def _on_fetch_error(self, message: str):
        self.loading_bar.setVisible(False)
        self.status.setText(
            tr("Could not fetch formats: {}").format(message))

    def _update_ok(self):
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.table.selectionModel()
                 and self.table.selectionModel().hasSelection()))

    def _on_selection(self):
        self._update_ok()
        rows = (self.table.selectionModel().selectedRows()
                if self.table.selectionModel() else [])
        if not rows or self._multi_urls:
            self.selected_bar.setVisible(False)
            return
        row = rows[0].row()
        name = " ".join(self.table.item(row, 0).text().split())
        if row == 0:
            # the right side already says «рекомендуется» — saying it
            # twice on one line read as a glitch
            name = name.split(" (")[0]
        self.selected_label.setText(
            tr("Selected:") + f" <b>{name}</b>")
        if row == 0:
            self.selected_detail.setText(tr("recommended"))
        else:
            parts = [self.table.item(row, 1).text(),
                     self.table.item(row, 3).text()]
            self.selected_detail.setText(
                " · ".join(part for part in parts if part))
        self.selected_bar.setVisible(True)

    # ---------------------------------------------------------- result
    def _accept_best(self):
        if not self._url() and not self._multi_urls:
            return
        self._use_best = True
        self.accept()

    def _selected_format(self):
        rows = self.table.selectionModel().selectedRows() \
            if self.table.selectionModel() else []
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    def result_item(self) -> QueueItem:
        info = self._info or {}
        fmt = None if self._use_best else self._selected_format()
        if fmt is None:
            spec, label = downloader.BEST_SPEC, downloader.BEST_LABEL
        else:
            spec = downloader.spec_for_format(fmt)
            label = downloader.format_label(fmt)
        return QueueItem(
            kind="url",
            url=info.get("url") or self._url(),
            format_spec=spec,
            format_label=label,
            title=info.get("title", ""),
            duration=info.get("duration"),
        )

    def result_items(self) -> list:
        """Batch mode: one item per pasted link at the chosen quality
        cap; otherwise the single (possibly format-picked) item."""
        if self._multi_urls:
            spec, label = downloader.quality_spec(self.quality())
            return [QueueItem(kind="url", url=u, format_spec=spec,
                              format_label=label)
                    for u in self._multi_urls]
        return [self.result_item()]
