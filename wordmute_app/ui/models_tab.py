"""Models tab: whisper models with per-row download/delete actions and
disk usage, GigaAM cache overview, device indicator."""

import subprocess

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import gpu, models
from .hover_table import HoverRowTable
from .i18n import tr

COL_MODEL, COL_STATUS, COL_SIZE, COL_ACTION = range(4)


class DownloadWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str, str)

    def __init__(self, model: str, parent=None):
        super().__init__(parent)
        self._model = model

    def run(self):
        try:
            models.download_whisper_model(self._model)
        except Exception as exc:
            self.failed.emit(self._model, str(exc))
        else:
            self.succeeded.emit(self._model)


class ModelsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._downloading = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        gpus = gpu.detect_gpus()
        if gpus:
            g = max(gpus, key=lambda x: x.vram_mb)
            device_text = f"GPU: {g.name} · {g.vram_mb / 1000:.1f} GB VRAM"
        else:
            device_text = tr("No NVIDIA GPU detected — use CPU mode in "
                             "Settings (roughly 2-4x slower).")
        gpu_label = QLabel(device_text)
        gpu_label.setProperty("muted", not gpus)
        layout.addWidget(gpu_label)

        layout.addWidget(QLabel("<b>Whisper</b>"))
        self.table = HoverRowTable(0, 4)
        self.table.setHorizontalHeaderLabels(
            [tr("Model"), tr("Status"), tr("Size"), ""])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        layout.addWidget(self.table)

        gigaam_row = QHBoxLayout()
        gigaam_row.setSpacing(8)
        self.gigaam_label = QLabel()
        self.gigaam_label.setWordWrap(True)
        gigaam_row.addWidget(self.gigaam_label, stretch=1)
        self.open_cache_button = QPushButton(tr("Open folder"))
        self.open_cache_button.setToolTip(str(models.hf_hub_cache()))
        self.open_cache_button.clicked.connect(self._open_cache)
        self.gigaam_delete_button = QPushButton(tr("Delete GigaAM caches"))
        self.gigaam_delete_button.setProperty("danger", True)
        self.gigaam_delete_button.clicked.connect(self._delete_gigaam)
        gigaam_row.addWidget(self.open_cache_button)
        gigaam_row.addWidget(self.gigaam_delete_button)
        layout.addLayout(gigaam_row)

        self.status_label = QLabel("")
        self.status_label.setProperty("muted", True)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.refresh()

    # ---------------------------------------------------------- data
    def refresh(self):
        status = models.whisper_model_status()
        self.table.setRowCount(len(status))
        for row, st in enumerate(status):
            model = st["model"]
            self.table.setItem(row, COL_MODEL, QTableWidgetItem(model))
            downloading = model == self._downloading
            status_text = (tr("downloading…") if downloading else
                           tr("downloaded ✓") if st["downloaded"]
                           else tr("not downloaded"))
            self.table.setItem(row, COL_STATUS,
                               QTableWidgetItem(status_text))
            self.table.setItem(row, COL_SIZE, QTableWidgetItem(
                models.fmt_size(st["size_bytes"]) if st["downloaded"]
                else ""))
            button = QPushButton(
                tr("Delete") if st["downloaded"] else tr("Download"))
            if st["downloaded"]:
                button.setProperty("danger", True)
            button.setEnabled(not downloading and self._worker is None)
            button.clicked.connect(
                lambda _=False, m=model, d=st["downloaded"]:
                self._delete(m) if d else self._download(m))
            self.table.setCellWidget(row, COL_ACTION, button)
        # natural height from the REAL row heights (the in-row buttons
        # make rows taller than any fixed guess), capped with an inner
        # scrollbar beyond that
        self.table.resizeRowsToContents()
        header = self.table.horizontalHeader()
        total = (max(header.height(), header.sizeHint().height())
                 + 2 * self.table.frameWidth() + 4
                 + sum(self.table.rowHeight(r)
                       for r in range(self.table.rowCount())))
        self.table.setFixedHeight(min(total, 420))

        caches = models.gigaam_cache_dirs()
        if caches:
            total = sum(size for _, size in caches)
            self.gigaam_label.setText(
                "<b>GigaAM</b>: "
                + tr("{} cached (models download automatically on "
                     "first use).").format(models.fmt_size(total)))
            self.gigaam_delete_button.setEnabled(True)
        else:
            self.gigaam_label.setText(
                "<b>GigaAM</b>: "
                + tr("nothing cached yet — models download automatically "
                     "on first use."))
            self.gigaam_delete_button.setEnabled(False)

    # ---------------------------------------------------------- actions
    def _download(self, model: str):
        if self._worker is not None:
            return
        self._downloading = model
        self.status_label.setText(
            tr("Downloading {}… (this can take a while; the app stays "
               "usable)").format(model))
        self._worker = DownloadWorker(model)
        self._worker.succeeded.connect(self._on_download_done)
        self._worker.failed.connect(self._on_download_failed)
        self._worker.start()
        self.refresh()

    def _on_download_done(self, model: str):
        self._worker = None
        self._downloading = None
        self.status_label.setText(f"{model} downloaded.")
        self.refresh()

    def _on_download_failed(self, model: str, message: str):
        self._worker = None
        self._downloading = None
        self.status_label.setText(f"Download of {model} failed: {message}")
        self.refresh()

    def _delete(self, model: str):
        if QMessageBox.question(
                self, "WordMute",
                tr("Delete the downloaded '{}' model? It will be "
                   "re-downloaded automatically the next time it's "
                   "used.").format(model)) \
                == QMessageBox.StandardButton.Yes:
            models.delete_whisper_model(model)
            self.refresh()

    def _delete_gigaam(self):
        if QMessageBox.question(
                self, "WordMute",
                tr("Delete all GigaAM model caches? They will be "
                   "re-downloaded on the next GigaAM pass.")) \
                == QMessageBox.StandardButton.Yes:
            models.delete_gigaam_caches()
            self.refresh()

    def _open_cache(self):
        subprocess.Popen(["explorer", str(models.hf_hub_cache())])

    def shutdown(self):
        if self._worker is not None:
            self._worker.wait(30000)
