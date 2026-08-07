"""One-time GigaAM setup wizard.

Walks through the Hugging Face steps that cannot be automated (account,
gated-model consent, access token), validates the token + pyannote
access online, and checks for the FFmpeg shared build. Whisper needs
none of this — the wizard exists so GigaAM can be an opt-in upgrade.
Layout per design spec: fixed width, three numbered step cards."""

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core import config, hf_setup
from ..engine import wordmute as engine
from .i18n import tr

INTRO_HTML = (
    "GigaAM is faster and noticeably more accurate for pure Russian "
    "speech, but its long-audio pipeline uses a <i>gated</i> model on "
    "Hugging Face — each user must accept its terms with their own free "
    "account. Three steps, needed once:")

# (link text, suffix, url) — link text and suffix translate separately
STEPS = [
    ("Create a free Hugging Face account", " (skip if you have one)",
     hf_setup.SIGNUP_URL),
    ("Open the pyannote/segmentation-3.0 page",
     " and fill in the short access form", hf_setup.CONSENT_URL),
    ("Create an access token",
     " (type: <b>read</b>) and paste it below", hf_setup.TOKEN_URL),
]

FFMPEG_HINT = ("GigaAM also needs FFmpeg's <i>shared</i> build (separate "
               "from the normal ffmpeg). Install it with "
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


def _step_card(number: int, html: str) -> QFrame:
    card = QFrame()
    card.setProperty("stepCard", True)
    row = QHBoxLayout(card)
    row.setContentsMargins(12, 10, 12, 10)
    row.setSpacing(12)
    badge = QLabel(str(number))
    badge.setProperty("stepNumber", True)
    row.addWidget(badge, alignment=Qt.AlignTop)
    text = QLabel(html)
    text.setWordWrap(True)
    text.setOpenExternalLinks(True)
    text.setTextFormat(Qt.RichText)
    row.addWidget(text, stretch=1)
    return card


class GigaamWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GigaAM Setup")
        self.setFixedWidth(560)
        self._worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        intro = QLabel(tr(INTRO_HTML))
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.RichText)
        layout.addWidget(intro)

        for i, (link, suffix, url) in enumerate(STEPS, start=1):
            html = f'<a href="{url}">{tr(link)}</a>{tr(suffix)}'
            layout.addWidget(_step_card(i, html))

        token_row = QHBoxLayout()
        token_row.setSpacing(8)
        self.token_edit = QLineEdit(config.load_hf_token())
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("hf_…")
        show = QCheckBox(tr("Show"))
        show.toggled.connect(
            lambda on: self.token_edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        token_row.addWidget(QLabel(tr("Token:")))
        token_row.addWidget(self.token_edit, stretch=1)
        token_row.addWidget(show)
        layout.addLayout(token_row)
        stored_note = QLabel(tr("Stored only on this computer."))
        stored_note.setProperty("muted", True)
        layout.addWidget(stored_note)

        validate_row = QHBoxLayout()
        self.validate_button = QPushButton("Validate && Save")
        self.validate_button.setProperty("primary", True)
        self.validate_button.clicked.connect(self._validate)
        validate_row.addWidget(self.validate_button)
        validate_row.addStretch()
        layout.addLayout(validate_row)

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

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_button = QPushButton(tr("Close"))
        close_button.clicked.connect(self.close)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    # ---------------------------------------------------------- checks
    def _check_ffmpeg(self):
        found = engine.discover_ffmpeg_shared_dir()
        if found:
            self.ffmpeg_status.setText(
                f"✓ FFmpeg shared build found: {found}")
            self.ffmpeg_status.setProperty("state", "ok")
            self.ffmpeg_status.setToolTip(str(found))
            self.recheck_button.setVisible(False)
        else:
            self.ffmpeg_status.setText("✗ " + tr(FFMPEG_HINT))
            self.ffmpeg_status.setProperty("state", "warn")
            self.recheck_button.setVisible(True)
        style = self.ffmpeg_status.style()
        style.unpolish(self.ffmpeg_status)
        style.polish(self.ffmpeg_status)

    def _validate(self):
        token = self.token_edit.text().strip()
        if not token:
            self.token_status.setText(tr("Paste a token first."))
            return
        self.validate_button.setEnabled(False)
        self.token_status.setText(tr("Checking token and model access…"))
        self._worker = ValidateWorker(token)
        self._worker.succeeded.connect(self._on_ok)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _set_status(self, text: str, state: str):
        self.token_status.setText(text)
        self.token_status.setProperty("state", state)
        style = self.token_status.style()
        style.unpolish(self.token_status)
        style.polish(self.token_status)

    def _on_ok(self, user: str):
        self._worker = None
        token = self.token_edit.text().strip()
        config.save_hf_token(token)
        os.environ["HF_TOKEN"] = token
        self.validate_button.setEnabled(True)
        self._set_status(
            tr("✓ Signed in as {}; pyannote access confirmed. Token "
               "saved — GigaAM passes are ready to use.").format(user),
            "ok")

    def _on_failed(self, message: str):
        self._worker = None
        self.validate_button.setEnabled(True)
        self._set_status(f"✗ {message}", "err")

    def closeEvent(self, event):
        if self._worker is not None:
            self._worker.wait(15000)
        event.accept()
