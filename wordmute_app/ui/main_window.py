"""Main window: file/folder queue with per-file progress, word list
selection, pass plan builder, settings dialog, run with live status."""

import os
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import config, gpu
from ..core.jobs import JobOptions, QueueItem, build_plan, expand_inputs
from ..core.probe import media_duration
from ..core.wordlists import merge_wordlists
from .events import format_event
from .gigaam_wizard import GigaamWizard
from .plan_widget import PassPlanWidget
from .review_dialog import ReviewDialog
from .settings_dialog import SettingsDialog
from .url_dialog import AddUrlDialog
from .worker import ProcessWorker

COL_FILE, COL_DURATION, COL_STATUS = 0, 1, 2


def fmt_duration(sec) -> str:
    if sec is None:
        return "—"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_eta(sec: float) -> str:
    if sec >= 90:
        return f"~{round(sec / 60)} min left"
    return f"~{max(1, int(sec))} s left"


def fmt_speed(bps) -> str:
    if not bps:
        return ""
    mbps = bps / (1024 * 1024)
    return f"{mbps:.1f} MB/s" if mbps >= 1 else f"{bps / 1024:.0f} KB/s"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WordMute")
        self.resize(960, 720)
        self.setAcceptDrops(True)

        self._worker = None
        self._wordlist_paths = config.ensure_user_wordlists()
        self._settings = config.load_settings()
        self._gpus = gpu.detect_gpus()
        self._reset_run_state(total=0)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- file queue
        file_buttons = QHBoxLayout()
        self.add_button = QPushButton("Add Files…")
        self.add_button.clicked.connect(self._pick_files)
        self.add_folder_button = QPushButton("Add Folder…")
        self.add_folder_button.clicked.connect(self._pick_folder)
        self.add_url_button = QPushButton("Add URL…")
        self.add_url_button.clicked.connect(self._add_url)
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._remove_selected)
        self.review_button = QPushButton("Review…")
        self.review_button.setToolTip(
            "Open a review file (saved next to each processed output) to "
            "listen to muted moments and un-mute false positives.")
        self.review_button.clicked.connect(self._pick_review)
        self.settings_button = QPushButton("Settings…")
        self.settings_button.clicked.connect(self._open_settings)
        file_buttons.addWidget(self.add_button)
        file_buttons.addWidget(self.add_folder_button)
        file_buttons.addWidget(self.add_url_button)
        file_buttons.addWidget(self.remove_button)
        self.gigaam_setup_button = QPushButton("GigaAM Setup…")
        self.gigaam_setup_button.setToolTip(
            "One-time Hugging Face setup required for GigaAM passes. "
            "Whisper works without any of this.")
        self.gigaam_setup_button.clicked.connect(self._open_gigaam_setup)
        file_buttons.addStretch()
        file_buttons.addWidget(self.review_button)
        file_buttons.addWidget(self.gigaam_setup_button)
        file_buttons.addWidget(self.settings_button)
        root.addLayout(file_buttons)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["File", "Duration", "Status"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_FILE, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_DURATION, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        root.addWidget(self.table, stretch=2)

        # --- word lists + pass plan
        options_row = QHBoxLayout()
        lists_box = QGroupBox("Word lists")
        lists_layout = QVBoxLayout(lists_box)
        self.russian_check = QCheckBox("Russian list")
        self.russian_check.setChecked(self._settings["use_russian"])
        self.english_check = QCheckBox("English list")
        self.english_check.setChecked(self._settings["use_english"])
        lists_layout.addWidget(self.russian_check)
        lists_layout.addWidget(self.english_check)
        self.force_passes_check = QCheckBox("Force all passes")
        self.force_passes_check.setChecked(self._settings["force_passes"])
        self.force_passes_check.setToolTip(
            "Run every pass even if an earlier one finds nothing; the final "
            "pass re-transcribes completely fresh, ignoring caches.")
        self.retranscribe_check = QCheckBox("Ignore cached transcripts")
        self.retranscribe_check.setToolTip(
            "Re-transcribe from scratch on the first pass (one-off; "
            "not remembered).")
        lists_layout.addWidget(self.force_passes_check)
        lists_layout.addWidget(self.retranscribe_check)
        lists_layout.addStretch()
        options_row.addWidget(lists_box, stretch=1)

        self.plan = PassPlanWidget()
        self.plan.set_engines(self._settings["plan"])
        self.plan.changed.connect(self._refresh_warnings)
        options_row.addWidget(self.plan, stretch=2)
        root.addLayout(options_row)

        self.warnings_label = QLabel("")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet("color: #b8860b;")
        self.warnings_label.setVisible(False)
        root.addWidget(self.warnings_label)
        self._refresh_warnings()

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
        run_row.addWidget(self.progress_bar, stretch=1)
        root.addLayout(run_row)

        self.status_label = QLabel("Ready.")
        root.addWidget(self.status_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        root.addWidget(self.log, stretch=1)

    # ---------------------------------------------------------- queue
    def _items(self):
        return [self.table.item(r, COL_FILE).data(Qt.UserRole)
                for r in range(self.table.rowCount())]

    def _row_duration(self, row: int):
        return self.table.item(row, COL_DURATION).data(Qt.UserRole)

    def _insert_row(self, item: QueueItem, status: str = "queued"):
        row = self.table.rowCount()
        self.table.insertRow(row)
        name_item = QTableWidgetItem(item.display_name)
        name_item.setData(Qt.UserRole, item)
        name_item.setToolTip(item.url if item.kind == "url"
                             else str(item.path))
        self.table.setItem(row, COL_FILE, name_item)
        dur_item = QTableWidgetItem(fmt_duration(item.duration))
        dur_item.setData(Qt.UserRole, item.duration)
        self.table.setItem(row, COL_DURATION, dur_item)
        self.table.setItem(row, COL_STATUS, QTableWidgetItem(status))

    def _add_files(self, paths):
        existing = {it.path for it in self._items() if it.kind == "file"}
        for p in expand_inputs(paths):
            if p in existing:
                continue
            existing.add(p)
            self._insert_row(QueueItem(kind="file", path=p,
                                       duration=media_duration(p)))

    def _add_url_row(self, item: QueueItem):
        self._insert_row(item, status=f"queued ({item.format_label})")

    def _add_url(self, url: str = ""):
        dialog = AddUrlDialog(self, url=url)
        if dialog.exec():
            self._add_url_row(dialog.result_item())

    def _pick_files(self):
        from ..engine.wordmute import MEDIA_EXTS
        exts = " ".join(f"*{e}" for e in sorted(MEDIA_EXTS))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add media files", "", f"Media files ({exts});;All files (*)")
        self._add_files(files)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add folder")
        if d:
            self._add_files([d])

    def _remove_selected(self):
        if self._worker is not None:
            return
        for row in sorted({i.row() for i in self.table.selectedIndexes()},
                          reverse=True):
            self.table.removeRow(row)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        self._add_files(u.toLocalFile() for u in mime.urls()
                        if u.isLocalFile())
        web = [u.toString() for u in mime.urls()
               if u.scheme() in ("http", "https")]
        if not web and mime.hasText() \
                and mime.text().strip().startswith(("http://", "https://")):
            web = [mime.text().strip()]
        if web:
            self._add_url(web[0])

    # ---------------------------------------------------------- review
    def _review_path_for_row(self, row: int):
        return self.table.item(row, COL_STATUS).data(Qt.UserRole)

    def _on_row_double_clicked(self, item):
        path = self._review_path_for_row(item.row())
        if path and Path(path).exists():
            ReviewDialog(path, self).exec()
        else:
            QMessageBox.information(
                self, "WordMute",
                "No review data for this row yet — it appears after the "
                "file has been processed and something was muted.")

    def _pick_review(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open review file", "",
            "WordMute review (*.wordmute.json);;All files (*)")
        if path:
            try:
                ReviewDialog(path, self).exec()
            except Exception as exc:
                QMessageBox.warning(self, "WordMute",
                                    f"Could not open review file: {exc}")

    # ---------------------------------------------------------- settings
    def _open_settings(self):
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            self._settings.update(dialog.values())
            config.save_settings(self._settings)
            self._refresh_warnings()

    def _open_gigaam_setup(self):
        GigaamWizard(self).exec()
        self._refresh_warnings()

    # ---------------------------------------------------------- warnings
    def _gigaam_ready(self) -> bool:
        return bool(config.load_hf_token() or os.environ.get("HF_TOKEN"))

    def _current_warnings(self) -> list:
        s = self._settings
        engines = self.plan.engines()
        plan = build_plan(engines, s["model"], s["gigaam_model"])
        warnings = gpu.plan_warnings(plan, s["device"], self._gpus)
        if "gigaam" in engines and not self._gigaam_ready():
            warnings.append(
                "GigaAM passes need a one-time Hugging Face setup — "
                "click 'GigaAM Setup…'.")
        return warnings

    def _refresh_warnings(self):
        warnings = self._current_warnings()
        self.warnings_label.setText("\n".join(f"⚠ {w}" for w in warnings))
        self.warnings_label.setVisible(bool(warnings))

    # ---------------------------------------------------------- run
    def _selected_wordlists(self):
        paths = []
        if self.russian_check.isChecked():
            paths.append(self._wordlist_paths["russian"])
        if self.english_check.isChecked():
            paths.append(self._wordlist_paths["english"])
        return paths

    def _reset_run_state(self, total: int):
        self._done_files = 0
        self._total_files = total
        self._current_row = None
        self._pass_n = 1
        self._pass_total = 1
        self._pass_engine = ""
        self._pass_pct = 0.0
        self._asr_wall_start = None

    def _start(self):
        items = self._items()
        if not items:
            QMessageBox.information(self, "WordMute", "Add some files first.")
            return
        lists = self._selected_wordlists()
        if not lists:
            QMessageBox.information(self, "WordMute",
                                    "Select at least one word list.")
            return
        engines = self.plan.engines()
        if not engines:
            QMessageBox.information(self, "WordMute",
                                    "Add at least one pass to the plan.")
            return
        if "gigaam" in engines and not self._gigaam_ready():
            answer = QMessageBox.question(
                self, "WordMute",
                "The plan includes GigaAM passes, but the one-time Hugging "
                "Face setup hasn't been completed — they will likely fail.\n\n"
                "Open the setup wizard now? (Choose No to try running "
                "anyway, e.g. if the models are already cached.)")
            if answer == QMessageBox.StandardButton.Yes:
                self._open_gigaam_setup()
                return
        saved_token = config.load_hf_token()
        if saved_token:  # validated via the wizard; GigaAM reads the env
            os.environ["HF_TOKEN"] = saved_token

        wordlist = merge_wordlists(lists)
        s = self._settings
        options = JobOptions(
            device=s["device"], language=s["language"], pad=s["pad_ms"],
            no_vad=not s["vad"],
            retranscribe=self.retranscribe_check.isChecked(),
            force_passes=self.force_passes_check.isChecked(),
        )
        plan = build_plan(engines, s["model"], s["gigaam_model"])
        output_dir = (Path(s["output_dir"])
                      if s["output_mode"] == "folder" and s["output_dir"]
                      else None)

        for row in range(self.table.rowCount()):
            self.table.item(row, COL_STATUS).setText("queued")

        self._reset_run_state(total=len(items))
        self._pass_total = len(plan)
        self._worker = ProcessWorker(items, wordlist, plan, options,
                                     output_dir=output_dir,
                                     download_dir=config.download_dir(s))
        self._worker.engine_event.connect(self._on_engine_event)
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_finished.connect(self._on_file_finished)
        self._worker.all_finished.connect(self._on_all_finished)
        self._set_running(True)
        n = sum(len(part) for part in wordlist)
        plan_text = " -> ".join(f"{e}({m})" for e, m in plan)
        self._append_log(f"Word list: {n} entries. Plan: {plan_text}."
                         + (f" Output: {output_dir}" if output_dir else ""))
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
        self.add_folder_button.setEnabled(not running)
        self.add_url_button.setEnabled(not running)
        self.remove_button.setEnabled(not running)
        self.settings_button.setEnabled(not running)
        for w in (self.russian_check, self.english_check, self.plan,
                  self.force_passes_check, self.retranscribe_check):
            w.setEnabled(not running)
        if running:
            self.progress_bar.setRange(0, self._total_files * 100)
            self.progress_bar.setValue(0)
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)

    # ---------------------------------------------------------- progress
    def _update_overall_progress(self):
        if not self._total_files:
            return
        pass_fraction = ((self._pass_n - 1) + min(self._pass_pct, 1.0)) \
            / max(self._pass_total, 1)
        value = self._done_files * 100 + int(min(pass_fraction, 0.99) * 100)
        self.progress_bar.setValue(value)

    def _set_row_status(self, text: str):
        if self._current_row is not None:
            self.table.item(self._current_row, COL_STATUS).setText(text)

    def _pass_prefix(self) -> str:
        if self._pass_total > 1:
            return f"pass {self._pass_n}/{self._pass_total} · "
        return ""

    # ---------------------------------------------------------- worker events
    def _append_log(self, text: str):
        self.log.appendPlainText(text)

    def _on_engine_event(self, event: str, data: dict):
        if event == "download_start":
            self._set_row_status("downloading…")
            self.status_label.setText(f"Downloading {data['url']}…")
        elif event == "download_progress":
            self._on_download_progress(data)
            return
        elif event == "download_done":
            self._on_download_done(data["path"])
        elif event == "review_saved":
            if self._current_row is not None:
                self.table.item(self._current_row, COL_STATUS).setData(
                    Qt.UserRole, data["path"])
        elif event == "pass_start":
            self._pass_n = data["n"]
            self._pass_engine = data["engine"]
            self._pass_pct = 0.0
        elif event == "asr_start":
            self._asr_wall_start = time.monotonic()
            engine_name = data["engine"]
            self._set_row_status(
                f"{self._pass_prefix()}transcribing ({engine_name})…")
        elif event == "asr_progress":
            self._on_asr_progress(data["minutes"])
            return
        elif event == "cache_hit":
            self._pass_pct = 0.9
            self._update_overall_progress()
        elif event == "words_count":
            self._pass_pct = max(self._pass_pct, 0.9)
            self._set_row_status(f"{self._pass_prefix()}matching…")
            self._update_overall_progress()
        elif event == "mute_start":
            self._set_row_status(f"{self._pass_prefix()}muting…")

        line = format_event(event, data)
        if line:
            self._append_log(line)

    def _on_download_progress(self, d: dict):
        downloaded, total = d.get("downloaded"), d.get("total")
        parts = []
        if downloaded and total:
            parts.append(f"downloading {downloaded / total:.0%}")
        elif downloaded:
            parts.append(f"downloading {downloaded / (1024 * 1024):.0f} MB")
        else:
            parts.append("downloading")
        speed = fmt_speed(d.get("speed"))
        if speed:
            parts.append(speed)
        if d.get("eta"):
            parts.append(fmt_eta(d["eta"]))
        self._set_row_status(" · ".join(parts))

    def _on_download_done(self, path: str):
        # the file is now local: show its real name and duration so
        # transcription progress/ETA work as for any local file
        if self._current_row is None:
            return
        p = Path(path)
        name_item = self.table.item(self._current_row, COL_FILE)
        name_item.setText(p.name)
        name_item.setToolTip(str(p))
        duration = media_duration(p)
        dur_item = self.table.item(self._current_row, COL_DURATION)
        dur_item.setText(fmt_duration(duration))
        dur_item.setData(Qt.UserRole, duration)

    def _on_asr_progress(self, minutes: float):
        processed = minutes * 60
        duration = (self._row_duration(self._current_row)
                    if self._current_row is not None else None)
        if duration:
            pct = min(processed / duration, 1.0)
            self._pass_pct = 0.9 * pct  # transcription ~= the whole pass
            text = f"{self._pass_prefix()}transcribing {pct:.0%}"
            if self._asr_wall_start and pct > 0.02:
                elapsed = time.monotonic() - self._asr_wall_start
                speed = processed / elapsed
                if speed > 0:
                    text += f" · {fmt_eta((duration - processed) / speed)}"
        else:
            text = f"{self._pass_prefix()}transcribing {minutes:.1f} min"
        self._set_row_status(text)
        self.status_label.setText(
            f"Transcribing… {minutes:.1f} min of audio processed")
        self._update_overall_progress()

    def _on_file_started(self, row: int, name: str):
        self._current_row = row
        self._pass_n = 1
        self._pass_pct = 0.0
        self._asr_wall_start = None
        self._set_row_status("processing…")
        self.status_label.setText(f"Processing {name}…")
        self._append_log(f"\n=== {name} ===")

    def _on_file_finished(self, row: int, ok: bool, error: str):
        self._done_files += 1
        self._pass_pct = 0.0
        has_review = ok and self._review_path_for_row(row)
        self.table.item(row, COL_STATUS).setText(
            ("done — double-click to review" if has_review else "done")
            if ok else (error if error == "cancelled"
                        else f"error: {error}"))
        if not ok and error != "cancelled":
            self._append_log(f"Error: {error}")
        self._update_overall_progress()

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
            "use_russian": self.russian_check.isChecked(),
            "use_english": self.english_check.isChecked(),
            "plan": self.plan.engines(),
            "force_passes": self.force_passes_check.isChecked(),
        })
        config.save_settings(self._settings)
        event.accept()
