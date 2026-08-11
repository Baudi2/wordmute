"""First-run component setup (slim installer): downloads the managed
Python runtime, engine packages and ffmpeg into the app data dir, with
live progress. Also serves as repair/add-components from the Models
tab."""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ..core import config, gpu, runtime_env
from .i18n import tr

# offered at first run; the model downloads on first USE, not here
MODEL_CHOICES = (
    ("large-v3", "large-v3 — best quality, ~3 GB"),
    ("medium", "medium — good compromise, ~1.5 GB"),
    ("small", "small — fastest, lowest accuracy, ~0.5 GB"),
)

INTRO = ("WordMute needs a few components that are downloaded once "
         "(they are not inside the installer to keep it small). "
         "Requirements: a stable internet connection and enough free "
         "disk space. In Russia, python.org / PyPI / Hugging Face may "
         "be blocked or throttled — a VPN may be required.")


class SetupWorker(QThread):
    log_line = Signal(str)
    stage = Signal(str)
    progress = Signal(int, int)  # done, total bytes (0 = unknown)
    finished_ok = Signal(bool, str)

    def __init__(self, steps, parent=None):
        super().__init__(parent)
        self._steps = steps  # [(stage_name, callable), ...]
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            for name, step in self._steps:
                self.stage.emit(name)
                self.progress.emit(0, 0)
                step(log=self.log_line.emit,
                     progress=lambda d, t: self.progress.emit(d, t),
                     cancelled=lambda: self._cancelled)
        except runtime_env.SetupCancelled:
            self.finished_ok.emit(False, tr("cancelled"))
        except Exception as exc:
            self.finished_ok.emit(False, str(exc))
        else:
            self.finished_ok.emit(True, "")


def _wrap(fn, **fixed):
    def step(log=None, progress=None, cancelled=None):
        fn(log=log, progress=progress, cancelled=cancelled, **fixed)
    return step


def _packages_step(packages):
    def step(log=None, progress=None, cancelled=None):
        runtime_env.install_packages(packages, log=log,
                                     cancelled=cancelled)
    return step


class SetupDialog(QDialog):
    def __init__(self, parent=None, first_run: bool = True):
        super().__init__(parent)
        self.setWindowTitle(tr("WordMute components"))
        self.resize(640, 620)
        self._worker = None
        self._done = False

        s = runtime_env.status()
        gpus = gpu.detect_gpus()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        intro = QLabel(tr(INTRO))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.whisper_check = QCheckBox(
            tr("Whisper speech recognition (required)"))
        self.whisper_check.setChecked(not s["faster_whisper"])
        self.whisper_check.setEnabled(not s["faster_whisper"])
        layout.addWidget(self.whisper_check)
        flavor_row = QHBoxLayout()
        flavor_row.addSpacing(24)
        self.gpu_radio = QRadioButton(
            tr("GPU (NVIDIA) — fast, ~1.6 GB download"))
        self.cpu_radio = QRadioButton(
            tr("CPU only — slower, ~0.3 GB download"))
        (self.gpu_radio if gpus else self.cpu_radio).setChecked(True)
        flavor_row.addWidget(self.gpu_radio)
        flavor_row.addWidget(self.cpu_radio)
        flavor_row.addStretch()
        layout.addLayout(flavor_row)

        self.ytdlp_check = QCheckBox(
            tr("Video downloads (yt-dlp) — ~10 MB"))
        self.ytdlp_check.setChecked(not s["yt_dlp"])
        self.ytdlp_check.setEnabled(not s["yt_dlp"])
        layout.addWidget(self.ytdlp_check)

        self.ffmpeg_check = QCheckBox(
            tr("ffmpeg (audio/video processing) — ~80 MB"))
        self.ffmpeg_check.setChecked(not s["ffmpeg"])
        self.ffmpeg_check.setEnabled(not s["ffmpeg"])
        layout.addWidget(self.ffmpeg_check)

        self.gigaam_check = QCheckBox(
            tr("GigaAM — better Russian recognition (experimental, "
               "~3.5 GB download)"))
        self.gigaam_check.setChecked(False)
        layout.addWidget(self.gigaam_check)

        # first run only: pick the recognition model size up front so a
        # weak PC / slow VPN doesn't silently get the 3 GB default
        self.model_radios = {}
        if first_run:
            caption = QLabel(
                tr("Recognition model (downloads on first use; "
                   "changeable later in Settings):"))
            caption.setProperty("muted", True)
            caption.setWordWrap(True)
            layout.addWidget(caption)
            # own group — must not merge with the GPU/CPU radio pair
            self._model_group = QButtonGroup(self)
            current = config.load_settings().get("model", "large-v3")
            for name, label in MODEL_CHOICES:
                row = QHBoxLayout()
                row.addSpacing(24)
                radio = QRadioButton(tr(label))
                radio.setChecked(name == current)
                self._model_group.addButton(radio)
                self.model_radios[name] = radio
                row.addWidget(radio)
                row.addStretch()
                layout.addLayout(row)

        note = QLabel(tr("Everything is installed under your user "
                         "folder; nothing needs administrator rights."))
        note.setProperty("muted", True)
        note.setWordWrap(True)
        layout.addWidget(note)

        self.stage_label = QLabel("")
        layout.addWidget(self.stage_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log_pane")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        layout.addWidget(self.log, stretch=1)

        buttons = QHBoxLayout()
        self.install_button = QPushButton(tr("Install"))
        self.install_button.setProperty("primary", True)
        self.install_button.clicked.connect(self._install)
        self.close_button = QPushButton(
            tr("Cancel") if first_run else tr("Close"))
        self.close_button.clicked.connect(self._close_clicked)
        buttons.addWidget(self.install_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    # ---------------------------------------------------------- install
    def _build_steps(self):
        s = runtime_env.status()
        steps = []
        needs_python = ((self.whisper_check.isChecked()
                         or self.ytdlp_check.isChecked()
                         or self.gigaam_check.isChecked())
                        and not (s["python"] and s["pip"]))
        if needs_python:
            steps.append((tr("Python runtime"),
                          _wrap(runtime_env.install_python)))
        if self.ffmpeg_check.isChecked():
            steps.append(("ffmpeg", _wrap(runtime_env.install_ffmpeg)))
        packages = []
        if self.whisper_check.isChecked():
            flavor = ("whisper_gpu" if self.gpu_radio.isChecked()
                      else "whisper_cpu")
            packages += runtime_env.COMPONENTS[flavor]["packages"]
        if self.ytdlp_check.isChecked():
            packages += runtime_env.COMPONENTS["ytdlp"]["packages"]
        if self.gigaam_check.isChecked():
            packages += runtime_env.COMPONENTS["gigaam"]["packages"]
        if packages:
            steps.append((tr("Packages"), _packages_step(packages)))
        return steps

    def _install(self):
        steps = self._build_steps()
        if not steps:
            self._done = True
            self.accept()
            return
        self.install_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self._worker = SetupWorker(steps)
        self._worker.log_line.connect(self.log.appendPlainText)
        self._worker.stage.connect(
            lambda name: self.stage_label.setText(
                tr("Installing: {}").format(name)))
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, done: int, total: int):
        if total:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(done / total * 100))
        else:
            self.progress_bar.setRange(0, 0)

    def _on_finished(self, ok: bool, message: str):
        self._worker = None
        self.progress_bar.setVisible(False)
        if ok:
            runtime_env.activate()
            self._done = True
            self.stage_label.setText(tr("Done — components installed."))
            self.install_button.setText(tr("Continue"))
            self.install_button.setEnabled(True)
            self.install_button.clicked.disconnect()
            self.install_button.clicked.connect(self.accept)
        else:
            self.stage_label.setText(
                tr("Setup failed: {}").format(message))
            self.log.appendPlainText(message)
            self.install_button.setEnabled(True)

    def accept(self):
        self._save_model_choice()
        super().accept()

    def _save_model_choice(self):
        for name, radio in self.model_radios.items():
            if radio.isChecked():
                settings = config.load_settings()
                if settings.get("model") != name:
                    settings["model"] = name
                    config.save_settings(settings)
                return

    def _close_clicked(self):
        if self._worker is not None:
            self._worker.cancel()
            self.stage_label.setText(tr("Cancelling…"))
            return
        (self.accept if self._done else self.reject)()

    def closeEvent(self, event):
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(30000)
        event.accept()
