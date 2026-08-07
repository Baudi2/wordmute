"""Main window: file queue, word list / whisper options, run with live
progress. Minimal functional draft — layout polish comes later."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import config
from ..core.jobs import JobOptions
from ..core.wordlists import merge_wordlists
from ..engine.wordmute import MEDIA_EXTS
from .events import format_event
from .worker import ProcessWorker

WHISPER_MODELS = ["large-v3", "medium", "small", "base"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WordMute")
        self.resize(900, 640)
        self.setAcceptDrops(True)

        self._worker = None
        self._wordlist_paths = config.ensure_user_wordlists()
        self._settings = config.load_settings()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- file queue
        file_buttons = QHBoxLayout()
        self.add_button = QPushButton("Add Files…")
        self.add_button.clicked.connect(self._pick_files)
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._remove_selected)
        file_buttons.addWidget(self.add_button)
        file_buttons.addWidget(self.remove_button)
        file_buttons.addStretch()
        root.addLayout(file_buttons)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["File", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(self.table, stretch=2)

        # --- options
        options = QGroupBox("Options")
        opt_row = QHBoxLayout(options)

        self.russian_check = QCheckBox("Russian list")
        self.russian_check.setChecked(self._settings["use_russian"])
        self.english_check = QCheckBox("English list")
        self.english_check.setChecked(self._settings["use_english"])
        opt_row.addWidget(self.russian_check)
        opt_row.addWidget(self.english_check)

        opt_row.addSpacing(16)
        opt_row.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(WHISPER_MODELS)
        if self._settings["model"] in WHISPER_MODELS:
            self.model_combo.setCurrentText(self._settings["model"])
        opt_row.addWidget(self.model_combo)

        opt_row.addWidget(QLabel("Device:"))
        self.device_combo = QComboBox()
        self.device_combo.addItems(["cuda", "cpu"])
        self.device_combo.setCurrentText(self._settings["device"])
        opt_row.addWidget(self.device_combo)

        opt_row.addWidget(QLabel("Passes:"))
        self.passes_spin = QSpinBox()
        self.passes_spin.setRange(1, 5)
        self.passes_spin.setValue(self._settings["passes"])
        opt_row.addWidget(self.passes_spin)
        opt_row.addStretch()
        root.addWidget(options)

        # --- run controls + live status
        run_row = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setEnabled(False)
        run_row.addWidget(self.start_button)
        run_row.addWidget(self.cancel_button)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        run_row.addWidget(self.progress_bar, stretch=1)
        root.addLayout(run_row)

        self.status_label = QLabel("Ready.")
        root.addWidget(self.status_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        root.addWidget(self.log, stretch=1)

    # ---------------------------------------------------------- queue
    def _file_paths(self):
        return [Path(self.table.item(r, 0).data(Qt.UserRole))
                for r in range(self.table.rowCount())]

    def _add_files(self, paths):
        existing = set(self._file_paths())
        for p in paths:
            p = Path(p)
            if p in existing or p.suffix.lower() not in MEDIA_EXTS:
                continue
            if ".clean" in p.suffixes or p.stem.endswith(".clean"):
                continue
            existing.add(p)
            row = self.table.rowCount()
            self.table.insertRow(row)
            item = QTableWidgetItem(p.name)
            item.setData(Qt.UserRole, str(p))
            item.setToolTip(str(p))
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem("queued"))

    def _pick_files(self):
        exts = " ".join(f"*{e}" for e in sorted(MEDIA_EXTS))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add media files", "", f"Media files ({exts});;All files (*)")
        self._add_files(files)

    def _remove_selected(self):
        if self._worker is not None:
            return
        for row in sorted({i.row() for i in self.table.selectedIndexes()},
                          reverse=True):
            self.table.removeRow(row)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self._add_files(u.toLocalFile() for u in event.mimeData().urls()
                        if u.isLocalFile())

    # ---------------------------------------------------------- run
    def _selected_wordlists(self):
        paths = []
        if self.russian_check.isChecked():
            paths.append(self._wordlist_paths["russian"])
        if self.english_check.isChecked():
            paths.append(self._wordlist_paths["english"])
        return paths

    def _start(self):
        files = self._file_paths()
        if not files:
            QMessageBox.information(self, "WordMute", "Add some files first.")
            return
        lists = self._selected_wordlists()
        if not lists:
            QMessageBox.information(self, "WordMute",
                                    "Select at least one word list.")
            return

        wordlist = merge_wordlists(lists)
        options = JobOptions(device=self.device_combo.currentText())
        plan = [("whisper", self.model_combo.currentText())] \
            * self.passes_spin.value()

        for row in range(self.table.rowCount()):
            self.table.item(row, 1).setText("queued")

        self._worker = ProcessWorker(files, wordlist, plan, options)
        self._worker.engine_event.connect(self._on_engine_event)
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_finished.connect(self._on_file_finished)
        self._worker.all_finished.connect(self._on_all_finished)
        self._set_running(True)
        n = len(wordlist[0]) + len(wordlist[1]) + len(wordlist[2]) \
            + len(wordlist[3])
        self._append_log(f"Word list: {n} entries loaded. "
                         f"Plan: {len(plan)} whisper pass(es).")
        self._worker.start()

    def _cancel(self):
        if self._worker is not None:
            self._worker.cancel()
            self.status_label.setText("Cancelling…")
            self.cancel_button.setEnabled(False)

    def _set_running(self, running: bool):
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.add_button.setEnabled(not running)
        self.remove_button.setEnabled(not running)
        for w in (self.russian_check, self.english_check, self.model_combo,
                  self.device_combo, self.passes_spin):
            w.setEnabled(not running)
        self.progress_bar.setRange(0, 0 if running else 1)
        if not running:
            self.progress_bar.setValue(0)

    # ---------------------------------------------------------- worker events
    def _append_log(self, text: str):
        self.log.appendPlainText(text)

    def _on_engine_event(self, event: str, data: dict):
        if event == "asr_progress":
            self.status_label.setText(
                f"Transcribing… {data['minutes']:.1f} min of audio processed")
            return
        line = format_event(event, data)
        if line:
            self._append_log(line)

    def _on_file_started(self, row: int, name: str):
        self.table.item(row, 1).setText("processing…")
        self.status_label.setText(f"Processing {name}…")
        self._append_log(f"\n=== {name} ===")

    def _on_file_finished(self, row: int, ok: bool, error: str):
        self.table.item(row, 1).setText(
            "done" if ok else (error if error == "cancelled"
                               else f"error: {error}"))
        if not ok and error != "cancelled":
            self._append_log(f"Error: {error}")

    def _on_all_finished(self, done: int, total: int):
        self._worker = None
        self._set_running(False)
        self.status_label.setText(f"Finished: {done}/{total} file(s) ok.")
        self._append_log(f"\nFinished: {done}/{total} file(s) ok.")

    # ---------------------------------------------------------- lifecycle
    def closeEvent(self, event):
        if self._worker is not None:
            if QMessageBox.question(
                    self, "WordMute",
                    "Processing is still running. Cancel and quit?") \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.cancel()
            self._worker.wait(15000)
        self._settings.update({
            "device": self.device_combo.currentText(),
            "model": self.model_combo.currentText(),
            "passes": self.passes_spin.value(),
            "use_russian": self.russian_check.isChecked(),
            "use_english": self.english_check.isChecked(),
        })
        config.save_settings(self._settings)
        event.accept()
