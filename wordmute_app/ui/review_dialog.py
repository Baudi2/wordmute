"""Review screen: table of muted intervals for one processed file.
Click a row to hear the original audio; uncheck false positives;
re-render rebuilds the output from the source in one ffmpeg pass using
the recorded intervals — never re-transcribes."""

import threading
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
from ..core.probe import media_duration
from ..engine import wordmute as engine
from ..engine.wordmute import fmt_ts
from .hover_table import HoverRowTable
from .i18n import tr
from .player import SnippetPlayer
from .waveform import WaveformStrip, WaveformWorker

COL_MUTE, COL_START, COL_END, COL_PASS, COL_ENGINE, COL_TEXT = range(6)


def _scoped_reporter(prev, thread_id, on_progress):
    """The engine reporter is process-global; while the queue is running
    it belongs to the queue worker (which paints statuses onto the
    active card). Route by thread identity: events raised by the
    re-render thread stay private to the dialog, events from any other
    thread keep flowing to the previous reporter untouched."""
    def reporter(event, data):
        if threading.get_ident() == thread_id:
            if event == "mute_progress":
                on_progress(data["seconds"])
        else:
            prev(event, data)
    return reporter


class ReRenderWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)
    progressed = Signal(float)  # seconds rendered

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._data = data

    def run(self):
        prev = engine._reporter
        reporter = _scoped_reporter(prev, threading.get_ident(),
                                    self.progressed.emit)
        engine.set_reporter(reporter)
        try:
            review.apply_review(self._data)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit()
        finally:
            # the queue worker may have finished meanwhile and reset the
            # reporter — only restore if ours is still installed
            if engine._reporter is reporter:
                engine.set_reporter(prev)


class ReviewDialog(QDialog):
    def __init__(self, review_path, parent=None):
        super().__init__(parent)
        self._data = review.load_review(review_path)
        self._player = SnippetPlayer()
        self._worker = None
        self._dirty = False
        self._saved_muted = self._muted_snapshot()
        self._filling = False
        self._source_ok = Path(self._data["source"]).exists()

        output_name = Path(self._data["output"]).name
        self.setWindowTitle(f"{tr('Review')} — {output_name}")
        self.resize(860, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QLabel(f"<b>{output_name}</b><br>"
                        f"{tr('Source')}: {self._data['source']}")
        header.setObjectName("review_summary")
        header.setWordWrap(True)
        layout.addWidget(header)
        if not self._source_ok:
            warn = QLabel(tr("⚠ The original file was moved or deleted — "
                             "playback and re-rendering are unavailable."))
            warn.setWordWrap(True)
            layout.addWidget(warn)

        self.table = HoverRowTable(0, 6)
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
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, stretch=1)

        # waveform of the audio around the selected interval — shows
        # WHERE the word sits before the user even presses play
        self._wave = WaveformStrip()
        self._wave_worker = None
        self._wave_pending = None
        self._wave_cache = {}
        layout.addWidget(self._wave)
        self._fill_table()

        self.counts_label = QLabel()
        layout.addWidget(self.counts_label)
        self.status_label = QLabel(
            tr("Click a row to hear the original audio around it. Uncheck "
               "intervals that should not be muted, then Re-render."))
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("muted", True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.stop_button = QPushButton(tr("Stop playback"))
        self.stop_button.clicked.connect(self._player.stop)
        self.mute_all_button = QPushButton(tr("Mute all"))
        self.mute_all_button.clicked.connect(lambda: self._set_all(True))
        self.unmute_all_button = QPushButton(tr("Unmute all"))
        self.unmute_all_button.clicked.connect(lambda: self._set_all(False))
        self.rerender_button = QPushButton(tr("Re-render output"))
        self.rerender_button.setProperty("primary", True)
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

    def _muted_snapshot(self) -> list:
        return [iv.get("muted", True) for iv in self._data["intervals"]]

    def _on_item_changed(self, item):
        if self._filling or item.column() != COL_MUTE:
            return
        # itemChanged also fires for cosmetic changes (the row-hover
        # highlight sets cell backgrounds) — only a real checkbox flip
        # counts, and dirty means "differs from the last-saved state",
        # so flipping a box back restores a clean dialog
        iv = self._data["intervals"][item.row()]
        muted = item.checkState() == Qt.Checked
        if iv.get("muted", True) == muted:
            return
        iv["muted"] = muted
        self._dirty = self._muted_snapshot() != self._saved_muted
        self._update_counts()

    def _set_all(self, muted: bool):
        for row in range(self.table.rowCount()):
            self.table.item(row, COL_MUTE).setCheckState(
                Qt.Checked if muted else Qt.Unchecked)

    def _update_counts(self):
        total = len(self._data["intervals"])
        unmuted = sum(1 for iv in self._data["intervals"]
                      if not iv.get("muted", True))
        text = tr("{} interval(s)").format(total)
        if unmuted:
            text += tr(" — {} will be un-muted on re-render").format(unmuted)
        self.counts_label.setText(text)

    # ---------------------------------------------------------- playback
    def _on_selection(self):
        if not self._source_ok:
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        iv = self._data["intervals"][row]
        self._show_waveform(row, iv)
        try:
            self._player.play(self._data["source"], iv["s"], iv["e"])
        except Exception as exc:
            self.status_label.setText(
                tr("Playback failed: {}").format(exc))

    def _show_waveform(self, row: int, iv: dict):
        cached = self._wave_cache.get(row)
        if cached:
            self._wave.set_peaks(*cached)
            return
        self._wave.clear()
        if self._wave_worker is not None:
            self._wave_pending = (row, iv)   # latest wins when free
            return
        worker = WaveformWorker(self._data["source"], row,
                                iv["s"], iv["e"], self)
        worker.ready.connect(self._on_waveform_ready)
        worker.finished.connect(self._on_waveform_worker_done)
        self._wave_worker = worker
        worker.start()

    def _on_waveform_worker_done(self):
        self._wave_worker = None
        if self._wave_pending is not None:
            row, iv = self._wave_pending
            self._wave_pending = None
            if row not in self._wave_cache:
                self._show_waveform(row, iv)

    def _on_waveform_ready(self, row, peaks, f0, f1):
        self._wave_cache[row] = (peaks, f0, f1)
        rows = self.table.selectionModel().selectedRows()
        if rows and rows[0].row() == row:
            self._wave.set_peaks(peaks, f0, f1)

    # ---------------------------------------------------------- re-render
    def _rerender(self):
        self._player.stop()
        self.rerender_button.setEnabled(False)
        self.status_label.setText(tr("Re-rendering…"))
        self._duration = media_duration(self._data["source"])
        self._worker = ReRenderWorker(self._data)
        self._worker.succeeded.connect(self._on_rerender_ok)
        self._worker.failed.connect(self._on_rerender_failed)
        self._worker.progressed.connect(self._on_rerender_progress)
        self._worker.start()

    def _on_rerender_progress(self, seconds: float):
        if self._duration:
            pct = min(seconds / self._duration, 1.0)
            self.status_label.setText(f"{tr('Re-rendering…')} {pct:.0%}")

    def _on_rerender_ok(self):
        self._worker = None
        self._dirty = False
        self._saved_muted = self._muted_snapshot()  # new baseline
        self.rerender_button.setEnabled(True)
        muted = sum(1 for iv in self._data["intervals"]
                    if iv.get("muted", True))
        self.status_label.setText(
            tr("Output updated: {} interval(s) muted.").format(muted))
        window = self.parent()
        if window is not None:  # toast on the MAIN window, never here
            from .toasts import show_toast
            show_toast(window, tr("Re-render finished"),
                       Path(self._data["output"]).name)

    def _on_rerender_failed(self, message: str):
        self._worker = None
        self.rerender_button.setEnabled(True)
        self.status_label.setText(
            tr("Re-render failed: {}").format(message))

    # ---------------------------------------------------------- lifecycle
    def closeEvent(self, event):
        if self._worker is not None:
            self._worker.wait()
        if self._wave_worker is not None:
            self._wave_worker.wait(5000)
        if self._dirty:
            if QMessageBox.question(
                    self, "WordMute",
                    tr("You changed the mute selection but didn't "
                       "re-render, so the output file is unchanged. "
                       "Close anyway?")) \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._player.dispose()
        event.accept()
