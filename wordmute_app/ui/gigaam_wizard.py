"""One-time GigaAM setup wizard.

Walks through the Hugging Face steps that cannot be automated (account,
gated-model consent, access token), validates the token + pyannote
access online, and checks for the FFmpeg shared build. Whisper needs
none of this — the wizard exists so GigaAM can be an opt-in upgrade."""

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core import config, hf_setup
from ..engine import wordmute as engine

INTRO_HTML = f"""
<b>GigaAM one-time setup</b><br><br>
GigaAM is faster and noticeably more accurate for pure Russian speech,
but its long-audio pipeline uses a <i>gated</i> voice-detection model
hosted on Hugging Face. Hugging Face requires each user to accept the
model's terms with their own (free) account — this cannot be bundled
with the app. Three steps, needed once:<br><br>
1. <a href="{hf_setup.SIGNUP_URL}">Create a free Hugging Face account</a>
   (skip if you have one)<br>
2. <a href="{hf_setup.CONSENT_URL}">Open the pyannote/segmentation-3.0
   page</a> and fill in the short access form<br>
3. <a href="{hf_setup.TOKEN_URL}">Create an access token</a>
   (type: <b>read</b>), then paste it below<br><br>
The token is stored only on this computer.
"""

FFMPEG_HINT = ("GigaAM also needs FFmpeg's <i>shared</i> build (separate "
               "from the normal ffmpeg). Install it with: "
               "<code>winget install Gyan.FFmpeg.Shared</code>, "
               "then click Re-check.")


class ValidateWorker(QThread):
    succeeded = Signal(str)  # account name
    failed = Signal(str)

    def __init__(self, token: str, parent=None):
        super().__init__(parent)
        self._token = token

    def run(self):
        try:
            user = hf_setup.validate_token(self._token)
            hf_setup.check_pyannote_access(self._token)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(user)


class GigaamWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GigaAM Setup")
        self.resize(560, 480)
        self._worker = None

        layout = QVBoxLayout(self)
        intro = QLabel(INTRO_HTML)
        intro.setWordWrap(True)
        intro.setOpenExternalLinks(True)
        layout.addWidget(intro)

        token_row = QHBoxLayout()
        self.token_edit = QLineEdit(config.load_hf_token())
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("hf_…")
        show = QCheckBox("Show")
        show.toggled.connect(
            lambda on: self.token_edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        token_row.addWidget(QLabel("Token:"))
        token_row.addWidget(self.token_edit, stretch=1)
        token_row.addWidget(show)
        layout.addLayout(token_row)

        self.validate_button = QPushButton("Validate && Save")
        self.validate_button.clicked.connect(self._validate)
        layout.addWidget(self.validate_button)

        self.token_status = QLabel("")
        self.token_status.setWordWrap(True)
        self.token_status.setOpenExternalLinks(True)
        layout.addWidget(self.token_status)

        self.ffmpeg_status = QLabel("")
        self.ffmpeg_status.setWordWrap(True)
        self.ffmpeg_status.setTextFormat(Qt.RichText)
        layout.addWidget(self.ffmpeg_status)
        recheck_row = QHBoxLayout()
        self.recheck_button = QPushButton("Re-check FFmpeg")
        self.recheck_button.clicked.connect(self._check_ffmpeg)
        recheck_row.addWidget(self.recheck_button)
        recheck_row.addStretch()
        layout.addLayout(recheck_row)
        self._check_ffmpeg()

        layout.addStretch()
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    # ---------------------------------------------------------- checks
    def _check_ffmpeg(self):
        found = engine.discover_ffmpeg_shared_dir()
        if found:
            self.ffmpeg_status.setText(
                f"✓ FFmpeg shared build found: {found}")
            self.recheck_button.setVisible(False)
        else:
            self.ffmpeg_status.setText("✗ " + FFMPEG_HINT)
            self.recheck_button.setVisible(True)

    def _validate(self):
        token = self.token_edit.text().strip()
        if not token:
            self.token_status.setText("Paste a token first.")
            return
        self.validate_button.setEnabled(False)
        self.token_status.setText("Checking token and model access…")
        self._worker = ValidateWorker(token)
        self._worker.succeeded.connect(self._on_ok)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_ok(self, user: str):
        self._worker = None
        token = self.token_edit.text().strip()
        config.save_hf_token(token)
        os.environ["HF_TOKEN"] = token
        self.validate_button.setEnabled(True)
        self.token_status.setText(
            f"✓ Signed in as {user}; pyannote access confirmed. "
            "Token saved — GigaAM passes are ready to use.")

    def _on_failed(self, message: str):
        self._worker = None
        self.validate_button.setEnabled(True)
        self.token_status.setText(f"✗ {message}")

    def closeEvent(self, event):
        if self._worker is not None:
            self._worker.wait(15000)
        event.accept()
