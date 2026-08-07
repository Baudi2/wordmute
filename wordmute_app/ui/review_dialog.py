"""Review screen: table of muted intervals for one processed file.
Click a row to hear the original audio; uncheck false positives;
re-render rebuilds the output from the source in one ffmpeg pass using
the recorded intervals — never re-transcribes."""

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core import review
from ..engine.wordmute import fmt_ts
from .i18n import tr
from .player import SnippetPlayer

COL_MUTE, COL_START, COL_END, COL_PASS, COL_ENGINE, COL_TEXT = range(6)


class ReRenderWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._data = data

    def run(self):
        try:
            review.apply_review(self._data)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit()


class ReviewDialog(QDialog):
    def __init__(self, review_path, parent=None):
        super().__init__(parent)
        self._data = review.load_review(review_path)
        self._player = SnippetPlayer()
        self._worker = None
        self._dirty = False
        self._filling = False
        self._source_ok = Path(self._data["source"]).exists()

        output_name = Path(self._data["output"]).name
        self.setWindowTitle(f"Review — {output_name}")
        self.resize(860, 560)
        layout = QVBoxLayout(self)

        header = QLabel(f"<b>{output_name}</b><br>"
                        f"Source: {self._data['source']}")
        header.setWordWrap(True)
        layout.addWidget(header)
        if not self._source_ok:
            warn = QLabel("⚠ The original file was moved or deleted — "
                          "playback and re-rendering are unavailable.")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [tr("Mute"), "Start", "End", tr("Pass"), tr("Engine"),
             tr("Words")])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self.table, stretch=1)
        self._fill_table()

        self.counts_label = QLabel()
        layout.addWidget(self.counts_label)
        self.status_label = QLabel(
            "Click a row to hear the original audio around it. Uncheck "
            "intervals that should not be muted, then Re-render.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.stop_button = QPushButton(tr("Stop playback"))
        self.stop_button.clicked.connect(self._player.stop)
        self.mute_all_button = QPushButton(tr("Mute all"))
        self.mute_all_button.clicked.connect(lambda: self._set_all(True))
        self.unmute_all_button = QPushButton(tr("Unmute all"))
        self.unmute_all_button.clicked.connect(lambda: self._set_all(False))
        self.rerender_button = QPushButton(tr("Re-render output"))
        self.rerender_button.clicked.connect(self._rerender)
        self.rerender_button.setEnabled(self._source_ok)
        close_button = QPushButton(tr("Close"))
        close_button.clicked.connect(self.close)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.mute_all_button)
        buttons.addWidget(self.unmute_all_button)
        buttons.addStretch()
        buttons.addWidget(self.rerender_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self._update_counts()

    # ---------------------------------------------------------- table
    def _fill_table(self):
        self._filling = True
        intervals = self._data["intervals"]
        self.table.setRowCount(len(intervals))
        for row, iv in enumerate(intervals):
            mute_item = QTableWidgetItem()
            mute_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                               | Qt.ItemIsSelectable)
            mute_item.setCheckState(
                Qt.Checked if iv.get("muted", True) else Qt.Unchecked)
            self.table.setItem(row, COL_MUTE, mute_item)
            self.table.setItem(row, COL_START,
                               QTableWidgetItem(fmt_ts(iv["s"])))
            self.table.setItem(row, COL_END, QTableWidgetItem(fmt_ts(iv["e"])))
            self.table.setItem(row, COL_PASS,
                               QTableWidgetItem(str(iv.get("pass", 1))))
            self.table.setItem(row, COL_ENGINE,
                               QTableWidgetItem(iv.get("engine", "")))
            self.table.setItem(row, COL_TEXT, QTableWidgetItem(iv["text"]))
        self._filling = False

    def _on_item_changed(self, item):
        if self._filling or item.column() != COL_MUTE:
            return
        iv = self._data["intervals"][item.row()]
        iv["muted"] = item.checkState() == Qt.Checked
        self._dirty = True
        self._update_counts()

    def _set_all(self, muted: bool):
        for row in range(self.table.rowCount()):
            self.table.item(row, COL_MUTE).setCheckState(
                Qt.Checked if muted else Qt.Unchecked)

    def _update_counts(self):
        total = len(self._data["intervals"])
        unmuted = sum(1 for iv in self._data["intervals"]
                      if not iv.get("muted", True))
        text = f"{total} interval(s)"
        if unmuted:
            text += f" — {unmuted} will be un-muted on re-render"
        self.counts_label.setText(text)

    # ---------------------------------------------------------- playback
    def _on_selection(self):
        if not self._source_ok:
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        iv = self._data["intervals"][rows[0].row()]
        try:
            self._player.play(self._data["source"], iv["s"], iv["e"])
        except Exception as exc:
            self.status_label.setText(f"Playback failed: {exc}")

    # ---------------------------------------------------------- re-render
    def _rerender(self):
        self._player.stop()
        self.rerender_button.setEnabled(False)
        self.status_label.setText("Re-rendering…")
        self._worker = ReRenderWorker(self._data)
        self._worker.succeeded.connect(self._on_rerender_ok)
        self._worker.failed.connect(self._on_rerender_failed)
        self._worker.start()

    def _on_rerender_ok(self):
        self._worker = None
        self._dirty = False
        self.rerender_button.setEnabled(True)
        muted = sum(1 for iv in self._data["intervals"]
                    if iv.get("muted", True))
        self.status_label.setText(
            f"Output updated: {muted} interval(s) muted.")

    def _on_rerender_failed(self, message: str):
        self._worker = None
        self.rerender_button.setEnabled(True)
        self.status_label.setText(f"Re-render failed: {message}")

    # ---------------------------------------------------------- lifecycle
    def closeEvent(self, event):
        if self._worker is not None:
            self._worker.wait()
        if self._dirty:
            if QMessageBox.question(
                    self, "WordMute",
                    "You changed the mute selection but didn't re-render, "
                    "so the output file is unchanged. Close anyway?") \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._player.dispose()
        event.accept()
