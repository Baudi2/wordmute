"""Transcript viewer: searchable word-level transcript from the cached
.words.json next to a media file, with SRT export."""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from PySide6.QtWidgets import QAbstractItemView

from ..core import transcript
from ..engine.wordmute import fmt_ts, norm
from .i18n import tr


class TranscriptDialog(QDialog):
    def __init__(self, media, parent=None):
        super().__init__(parent)
        self._media = Path(media)
        self._words, engine_name = transcript.load_transcript(self._media)
        self._blocks = transcript.group_words(self._words)

        self.setWindowTitle(f"{self._media.name} — {engine_name}")
        self.resize(720, 560)
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Search:")))
        self.search = QLineEdit()
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, stretch=1)
        self.count_label = QLabel(f"{len(self._words)} words")
        top.addWidget(self.count_label)
        layout.addLayout(top)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Time", "Text"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        layout.addWidget(self.table, stretch=1)
        self._fill()

        buttons = QHBoxLayout()
        export = QPushButton(tr("Export SRT…"))
        export.clicked.connect(self._export_srt)
        buttons.addWidget(export)
        buttons.addStretch()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)

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
        default = str(self._media.with_suffix(".srt"))
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Export SRT…").rstrip("…"), default,
            "SubRip subtitles (*.srt)")
        if path:
            Path(path).write_text(transcript.words_to_srt(self._words),
                                  encoding="utf-8")
            self.count_label.setText(f"→ {Path(path).name}")
