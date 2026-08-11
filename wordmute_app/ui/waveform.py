"""Audio waveform strip for the review screen.

On row selection, ffmpeg extracts a small window around the muted
interval (±2 s context) as raw 8 kHz PCM; peak amplitudes render as
bars with the to-be-muted span highlighted in the mute color. The
user sees WHERE the word sits before even pressing play. No numpy —
array('h') peak-folding is plenty at this resolution."""

import subprocess
from array import array

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

ACCENT = QColor("#9184d9")            # speech bars (both themes)
MUTED = QColor("#e5484d")             # the interval being muted
CONTEXT_S = 2.0                       # context either side of the word
BARS = 120
RATE = 8000


class WaveformWorker(QThread):
    ready = Signal(int, list, float, float)  # row, peaks, from/to fracs

    def __init__(self, source, row: int, start: float, end: float,
                 parent=None):
        super().__init__(parent)
        self._source = str(source)
        self._row = row
        self._start = start
        self._end = end

    def run(self):
        win_start = max(0.0, self._start - CONTEXT_S)
        span = (self._end + CONTEXT_S) - win_start
        cmd = ["ffmpeg", "-v", "error",
               "-ss", f"{win_start:.3f}", "-t", f"{span:.3f}",
               "-i", self._source, "-vn", "-ac", "1", "-ar", str(RATE),
               "-f", "s16le", "-"]
        try:
            raw = subprocess.run(cmd, capture_output=True,
                                 timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired):
            return
        usable = len(raw) - (len(raw) % 2)
        if not usable:
            return
        samples = array("h")
        samples.frombytes(raw[:usable])
        n = len(samples)
        chunk = max(1, n // BARS)
        peaks = []
        for i in range(0, n - chunk + 1, chunk):
            seg = samples[i:i + chunk]
            peaks.append(max(abs(v) for v in seg) / 32768.0)
        total_s = n / RATE
        if not peaks or not total_s:
            return
        f0 = max(0.0, min((self._start - win_start) / total_s, 1.0))
        f1 = max(f0, min((self._end - win_start) / total_s, 1.0))
        self.ready.emit(self._row, peaks[:BARS], f0, f1)


class WaveformStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self._peaks = []
        self._f0 = self._f1 = 0.0

    def clear(self):
        self._peaks = []
        self.update()

    def set_peaks(self, peaks, f0: float, f1: float):
        self._peaks = list(peaks)
        self._f0, self._f1 = f0, f1
        self.update()

    def paintEvent(self, event):
        if not self._peaks:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        mid = height / 2
        n = len(self._peaks)
        bar_w = width / n
        painter.setPen(Qt.NoPen)
        for i, peak in enumerate(self._peaks):
            frac = (i + 0.5) / n
            painter.setBrush(MUTED if self._f0 <= frac <= self._f1
                             else ACCENT)
            bar_h = max(2.0, peak * (height - 8))
            painter.drawRoundedRect(i * bar_w + bar_w * 0.15,
                                    mid - bar_h / 2,
                                    bar_w * 0.7, bar_h, 1, 1)
        painter.end()
