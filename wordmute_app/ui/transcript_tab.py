"""Transcript tab: open a processed media file, browse/search its
cached transcript, export SRT. Cache-only — never transcribes."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import transcript
from ..engine.wordmute import MEDIA_EXTS, fmt_ts, norm
from .hover_table import HoverRowTable
from .i18n import tr


class TranscriptTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._media = None
        self._words = []
        self._blocks = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(8)
        open_button = QPushButton(tr("Open Media…"))
        open_button.clicked.connect(self._pick_media)
        top.addWidget(open_button)
        self.file_label = QLabel(tr("No file opened."))
        self.file_label.setProperty("muted", True)
        top.addWidget(self.file_label, stretch=1)
        layout.addLayout(top)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(tr("Search:")))
        self.search = QLineEdit()
        self.search.textChanged.connect(self._filter)
        search_row.addWidget(self.search, stretch=1)
        self.count_label = QLabel("")
        self.count_label.setProperty("muted", True)
        search_row.addWidget(self.count_label)
        layout.addLayout(search_row)

        # design 1g: the same empty-state shell as the queue, but with
        # accepts="false" — nothing can be dropped here
        self.empty_state = QFrame()
        self.empty_state.setObjectName("drop_zone")
        self.empty_state.setProperty("accepts", "false")
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.addStretch()
        icon = QLabel("¶")
        icon.setObjectName("empty_icon")
        icon.setProperty("accepts", "false")
        icon.setAlignment(Qt.AlignCenter)
        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon)
        icon_row.addStretch()
        empty_layout.addLayout(icon_row)
        empty_layout.addSpacing(12)
        title = QLabel(tr("The transcript will appear here"))
        title.setObjectName("empty_title")
        title.setAlignment(Qt.AlignCenter)
        body = QLabel(tr("Processed files open from here — or from "
                         "History with a double click."))
        body.setObjectName("empty_body")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        empty_layout.addWidget(title)
        empty_layout.addWidget(body)
        buttons = QHBoxLayout()
        buttons.addStretch()
        open_history = QPushButton(tr("Open History"))
        open_history.setObjectName("btn_empty_secondary")
        open_history.clicked.connect(self._goto_history)
        buttons.addWidget(open_history)
        buttons.addStretch()
        empty_layout.addSpacing(12)
        empty_layout.addLayout(buttons)
        empty_layout.addStretch()

        self.table = HoverRowTable(0, 2)
        self.table.setHorizontalHeaderLabels([tr("Time"), tr("Text")])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.table)
        layout.addWidget(self.stack, stretch=1)

        bottom = QHBoxLayout()
        self.export_button = QPushButton(tr("Export SRT…"))
        self.export_button.clicked.connect(self._export_srt)
        self.export_button.setEnabled(False)
        bottom.addWidget(self.export_button)
        bottom.addStretch()
        layout.addLayout(bottom)

        self.status_label = QLabel(
            tr("Open a processed media file to view its transcript "
               "(the cache appears after transcription)."))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _goto_history(self):
        window = self.window()
        if hasattr(window, "tabs") and hasattr(window, "history_tab"):
            window.tabs.setCurrentWidget(window.history_tab)

    def _pick_media(self):
        exts = " ".join(f"*{e}" for e in sorted(MEDIA_EXTS))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open media file", "", f"Media files ({exts})")
        if path:
            self.load_media(path)

    def load_media(self, path):
        try:
            self._words, engine_name = transcript.load_transcript(path)
        except FileNotFoundError as exc:
            self.status_label.setText(str(exc))
            return
        self._media = Path(path)
        self._blocks = transcript.group_words(self._words)
        self.file_label.setText(f"{self._media.name} — {engine_name}")
        self.count_label.setText(tr("{} words").format(len(self._words)))
        self.status_label.setText("")
        self.export_button.setEnabled(True)
        self.search.clear()
        self._fill()
        self.stack.setCurrentWidget(self.table)

    def _fill(self):
        from PySide6.QtGui import QFont
        mono = QFont("Cascadia Mono")
        mono.setStyleHint(QFont.Monospace)
        self.table.setRowCount(len(self._blocks))
        for row, block in enumerate(self._blocks):
            time_item = QTableWidgetItem(fmt_ts(block[0]["s"]))
            time_item.setFont(mono)
            self.table.setItem(row, 0, time_item)
            self.table.setItem(
                row, 1,
                QTableWidgetItem(" ".join(w["w"] for w in block)))
        self.table.resizeRowsToContents()

    def _filter(self, needle: str):
        needle = norm(needle.strip())
        visible = 0
        for row, block in enumerate(self._blocks):
            if needle:
                text = " ".join(norm(w["w"]) for w in block)
                hide = needle not in text
            else:
                hide = False
            if not hide:
                visible += 1
            self.table.setRowHidden(row, hide)
        if needle:
            self.count_label.setText(
                tr("{} of {} blocks").format(visible, len(self._blocks)))
        elif self._words:
            self.count_label.setText(
                tr("{} words").format(len(self._words)))

    def _export_srt(self):
        if not self._media:
            return
        default = str(self._media.with_suffix(".srt"))
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Export SRT…").rstrip("…"), default,
            "SubRip subtitles (*.srt)")
        if path:
            Path(path).write_text(transcript.words_to_srt(self._words),
                                  encoding="utf-8")
            self.status_label.setText(f"→ {path}")
