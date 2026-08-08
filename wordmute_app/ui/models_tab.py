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

from ..core import gpu, models, updates
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


class CheckUpdatesWorker(QThread):
    result = Signal(dict)

    def run(self):
        self.result.emit({
            "packages": updates.check_packages(),
            "models": updates.check_whisper_models(),
        })


class UpgradeWorker(QThread):
    finished_ok = Signal(bool, str)

    def __init__(self, package_names, model_names, parent=None):
        super().__init__(parent)
        self._packages = list(package_names)
        self._models = list(model_names)

    def run(self):
        messages = []
        ok = True
        if self._packages:
            pip_ok, tail = updates.pip_upgrade(self._packages)
            ok = ok and pip_ok
            messages.append(tail if not pip_ok
                            else ", ".join(self._packages))
        for model in self._models:
            try:  # snapshot_download fetches the new revision
                models.download_whisper_model(model)
            except Exception as exc:
                ok = False
                messages.append(f"{model}: {exc}")
        self.finished_ok.emit(ok, "\n".join(messages))


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

        # ---- updates
        layout.addWidget(QLabel("<b>" + tr("Updates") + "</b>"))
        updates_row = QHBoxLayout()
        updates_row.setSpacing(8)
        self.check_updates_button = QPushButton(tr("Check for updates"))
        self.check_updates_button.clicked.connect(self._check_updates)
        self.update_all_button = QPushButton(tr("Update all"))
        self.update_all_button.setProperty("primary", True)
        self.update_all_button.setVisible(False)
        self.update_all_button.clicked.connect(self._update_all)
        updates_row.addWidget(self.check_updates_button)
        updates_row.addWidget(self.update_all_button)
        updates_row.addStretch()
        layout.addLayout(updates_row)
        self.updates_label = QLabel("")
        self.updates_label.setProperty("muted", True)
        self.updates_label.setWordWrap(True)
        layout.addWidget(self.updates_label)
        self._updates_worker = None
        self._upgrade_worker = None
        self._outdated_packages = []
        self._outdated_models = []

        layout.addStretch()
        self.refresh()

    # ---------------------------------------------------------- data
    def refresh(self):
        status = models.whisper_model_status()
        self.table.setRowCount(len(status))
        row_height = 34
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
            # Qt's row sizing ignores cell widgets: rows must be sized
            # to the button height explicitly or the buttons clip
            row_height = max(row_height, button.sizeHint().height() + 10)
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, row_height)
        header = self.table.horizontalHeader()
        total = (max(header.height(), header.sizeHint().height())
                 + 2 * self.table.frameWidth() + 6
                 + row_height * self.table.rowCount())
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

    # ---------------------------------------------------------- updates
    def _check_updates(self):
        if self._updates_worker is not None:
            return
        self.check_updates_button.setEnabled(False)
        self.update_all_button.setVisible(False)
        self.updates_label.setText(tr("Checking for updates…"))
        self._updates_worker = CheckUpdatesWorker()
        self._updates_worker.result.connect(self._on_updates_result)
        self._updates_worker.start()

    def _on_updates_result(self, result: dict):
        self._updates_worker = None
        self.check_updates_button.setEnabled(True)
        lines = []
        self._outdated_packages = []
        self._outdated_models = []
        for pkg in result["packages"]:
            if pkg["installed"] is None:
                lines.append(f"{pkg['name']}: {tr('not installed')}")
            elif pkg["latest"] is None:
                lines.append(f"{pkg['name']}: {pkg['installed']} — "
                             + tr("could not check"))
            elif pkg["update"]:
                lines.append(f"{pkg['name']}: {pkg['installed']} → "
                             f"{pkg['latest']}")
                self._outdated_packages.append(pkg["name"])
            else:
                lines.append(f"{pkg['name']}: {pkg['installed']} ✓")
        for m in result["models"]:
            if m["update"]:
                lines.append(
                    tr("whisper {}: new model revision available")
                    .format(m["model"]))
                self._outdated_models.append(m["model"])
            else:
                lines.append(f"whisper {m['model']} ✓")
        lines.append(tr("GigaAM weights update together with the "
                        "gigaam package."))
        self.updates_label.setText("\n".join(lines))
        self.update_all_button.setVisible(
            bool(self._outdated_packages or self._outdated_models))

    def _update_all(self):
        if self._upgrade_worker is not None:
            return
        self.update_all_button.setEnabled(False)
        self.check_updates_button.setEnabled(False)
        self.updates_label.setText(tr("Updating…"))
        self._upgrade_worker = UpgradeWorker(self._outdated_packages,
                                             self._outdated_models)
        self._upgrade_worker.finished_ok.connect(self._on_upgrade_done)
        self._upgrade_worker.start()

    def _on_upgrade_done(self, ok: bool, message: str):
        had_packages = bool(self._outdated_packages)
        self._upgrade_worker = None
        self.update_all_button.setEnabled(True)
        self.update_all_button.setVisible(not ok)
        self.check_updates_button.setEnabled(True)
        if ok:
            text = tr("Updates installed.")
            if had_packages:
                text += " " + tr("Restart the app to use them.")
            self.updates_label.setText(text)
        else:
            self.updates_label.setText(
                tr("Update failed: {}").format(message))
        self.refresh()

    def shutdown(self):
        for worker in (self._worker, self._updates_worker,
                       self._upgrade_worker):
            if worker is not None:
                worker.wait(30000)
