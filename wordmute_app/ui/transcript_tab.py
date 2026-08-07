"""Transcript tab: open a processed media file, browse/search its
cached transcript, export SRT. Cache-only — never transcribes."""

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import transcript
from ..engine.wordmute import MEDIA_EXTS, fmt_ts, norm
from .i18n import tr


class TranscriptTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._media = None
        self._words = []
        self._blocks = []

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        open_button = QPushButton(tr("Open Media…"))
        open_button.clicked.connect(self._pick_media)
        top.addWidget(open_button)
        self.file_label = QLabel(tr("No file opened."))
        top.addWidget(self.file_label, stretch=1)
        layout.addLayout(top)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(tr("Search:")))
        self.search = QLineEdit()
        self.search.textChanged.connect(self._filter)
        search_row.addWidget(self.search, stretch=1)
        self.count_label = QLabel("")
        search_row.addWidget(self.count_label)
        layout.addLayout(search_row)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Time", "Text"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        layout.addWidget(self.table, stretch=1)

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
        self.count_label.setText(f"{len(self._words)} words")
        self.status_label.setText("")
        self.export_button.setEnabled(True)
        self.search.clear()
        self._fill()

    def _fill(self):
        self.table.setRowCount(len(self._blocks))
        for row, block in enumerate(self._blocks):
            self.table.setItem(row, 0,
                               QTableWidgetItem(fmt_ts(block[0]["s"])))
            self.table.setItem(
                row, 1,
                QTableWidgetItem(" ".join(w["w"] for w in block)))
        self.table.resizeRowsToContents()

    def _filter(self, needle: str):
        needle = norm(needle.strip())
        for row, block in enumerate(self._blocks):
            if needle:
                text = " ".join(norm(w["w"]) for w in block)
                hide = needle not in text
            else:
                hide = False
            self.table.setRowHidden(row, hide)

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
