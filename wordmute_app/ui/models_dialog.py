"""Model manager: whisper model download/delete with disk usage, GigaAM
cache overview, device indicator."""

import subprocess

from PySide6.QtCore import QThread, Signal
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

from ..core import gpu, models
from .i18n import tr


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


class ModelsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Model Manager…").rstrip("…"))
        self.resize(560, 480)
        self._worker = None
        layout = QVBoxLayout(self)

        gpus = gpu.detect_gpus()
        if gpus:
            g = max(gpus, key=lambda x: x.vram_mb)
            device_text = f"GPU: {g.name} ({g.vram_mb / 1000:.1f} GB VRAM)"
        else:
            device_text = ("No NVIDIA GPU detected — use CPU mode in "
                           "Settings (roughly 2-4x slower).")
        layout.addWidget(QLabel(device_text))

        layout.addWidget(QLabel("<b>Whisper</b>"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Model", "Status", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        buttons = QHBoxLayout()
        self.download_button = QPushButton(tr("Download"))
        self.download_button.clicked.connect(self._download_selected)
        self.delete_button = QPushButton(tr("Delete"))
        self.delete_button.clicked.connect(self._delete_selected)
        buttons.addWidget(self.download_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.gigaam_label = QLabel()
        self.gigaam_label.setWordWrap(True)
        layout.addWidget(self.gigaam_label)
        gigaam_row = QHBoxLayout()
        self.gigaam_delete_button = QPushButton("Delete GigaAM caches")
        self.gigaam_delete_button.clicked.connect(self._delete_gigaam)
        gigaam_row.addWidget(self.gigaam_delete_button)
        gigaam_row.addStretch()
        layout.addLayout(gigaam_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        close_row = QHBoxLayout()
        open_cache = QPushButton(tr("Open folder"))
        open_cache.setToolTip(str(models.hf_hub_cache()))
        open_cache.clicked.connect(self._open_cache)
        close_row.addWidget(open_cache)
        close_row.addStretch()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        close_row.addWidget(close)
        layout.addLayout(close_row)
        self.refresh()

    # ---------------------------------------------------------- data
    def refresh(self):
        status = models.whisper_model_status()
        self.table.setRowCount(len(status))
        for row, st in enumerate(status):
            self.table.setItem(row, 0, QTableWidgetItem(st["model"]))
            self.table.setItem(row, 1, QTableWidgetItem(
                "downloaded" if st["downloaded"] else "not downloaded"))
            self.table.setItem(row, 2, QTableWidgetItem(
                models.fmt_size(st["size_bytes"]) if st["downloaded"]
                else ""))
        caches = models.gigaam_cache_dirs()
        if caches:
            total = sum(size for _, size in caches)
            self.gigaam_label.setText(
                f"<b>GigaAM</b>: {models.fmt_size(total)} cached "
                "(models download automatically on first use).")
            self.gigaam_delete_button.setEnabled(True)
        else:
            self.gigaam_label.setText(
                "<b>GigaAM</b>: nothing cached yet — models download "
                "automatically on first use.")
            self.gigaam_delete_button.setEnabled(False)

    def _selected_model(self):
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).text() if rows else None

    # ---------------------------------------------------------- actions
    def _download_selected(self):
        model = self._selected_model()
        if not model or self._worker is not None:
            return
        self.download_button.setEnabled(False)
        self.status_label.setText(
            f"Downloading {model}… (this can take a while; the app stays "
            "usable)")
        self._worker = DownloadWorker(model)
        self._worker.succeeded.connect(self._on_download_done)
        self._worker.failed.connect(self._on_download_failed)
        self._worker.start()

    def _on_download_done(self, model: str):
        self._worker = None
        self.download_button.setEnabled(True)
        self.status_label.setText(f"{model} downloaded.")
        self.refresh()

    def _on_download_failed(self, model: str, message: str):
        self._worker = None
        self.download_button.setEnabled(True)
        self.status_label.setText(f"Download of {model} failed: {message}")

    def _delete_selected(self):
        model = self._selected_model()
        if not model:
            return
        if QMessageBox.question(
                self, "WordMute",
                f"Delete the downloaded '{model}' model? It will be "
                "re-downloaded automatically the next time it's used.") \
                == QMessageBox.StandardButton.Yes:
            models.delete_whisper_model(model)
            self.refresh()

    def _delete_gigaam(self):
        if QMessageBox.question(
                self, "WordMute",
                "Delete all GigaAM model caches? They will be re-downloaded "
                "on the next GigaAM pass.") \
                == QMessageBox.StandardButton.Yes:
            models.delete_gigaam_caches()
            self.refresh()

    def _open_cache(self):
        subprocess.Popen(["explorer", str(models.hf_hub_cache())])

    def closeEvent(self, event):
        if self._worker is not None:
            self.status_label.setText("Waiting for the download to stop…")
            self._worker.wait(30000)
        event.accept()
