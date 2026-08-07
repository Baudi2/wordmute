"""Settings tab. Unlike the old modal dialog, changes apply and persist
immediately; a `changed` signal lets the main window refresh advice
(GPU warnings etc.). Settings never affect a run already in progress —
options are captured at Start."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core import config
from .i18n import tr

WHISPER_MODELS = ["large-v3", "medium", "small", "base"]
GIGAAM_MODELS = ["v3_e2e_rnnt", "v3_e2e_ctc", "v3_rnnt", "v3_ctc"]


class SettingsTab(QWidget):
    changed = Signal()

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._loading = True

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.model_combo = QComboBox()
        self.model_combo.addItems(WHISPER_MODELS)
        if settings["model"] in WHISPER_MODELS:
            self.model_combo.setCurrentText(settings["model"])
        form.addRow(tr("Whisper model:"), self.model_combo)

        self.gigaam_combo = QComboBox()
        self.gigaam_combo.addItems(GIGAAM_MODELS)
        if settings["gigaam_model"] in GIGAAM_MODELS:
            self.gigaam_combo.setCurrentText(settings["gigaam_model"])
        form.addRow(tr("GigaAM model:"), self.gigaam_combo)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["cuda", "cpu"])
        self.device_combo.setCurrentText(settings["device"])
        form.addRow(tr("Device:"), self.device_combo)

        self.pad_spin = QSpinBox()
        self.pad_spin.setRange(0, 1000)
        self.pad_spin.setSingleStep(10)
        self.pad_spin.setSuffix(" ms")
        self.pad_spin.setValue(settings["pad_ms"])
        self.pad_spin.setToolTip("Extra silence around each muted word; "
                                 "never bleeds into neighboring words.")
        form.addRow(tr("Mute padding:"), self.pad_spin)

        self.language_edit = QLineEdit(settings["language"])
        self.language_edit.setToolTip("Whisper language code (e.g. ru, en); "
                                      "ignored by GigaAM passes.")
        form.addRow(tr("Whisper language:"), self.language_edit)

        beep_row = QHBoxLayout()
        self.beep_check = QCheckBox(tr("Beep instead of silence"))
        self.beep_check.setChecked(bool(settings.get("beep_hz", 0)))
        self.beep_check.setToolTip(
            "Replace muted words with a beep tone instead of silence. "
            "Note: files with several audio tracks keep only the first "
            "one in beep mode.")
        self.beep_spin = QSpinBox()
        self.beep_spin.setRange(200, 4000)
        self.beep_spin.setSingleStep(100)
        self.beep_spin.setSuffix(" Hz")
        self.beep_spin.setValue(settings.get("beep_hz", 0) or 1000)
        self.beep_spin.setEnabled(self.beep_check.isChecked())
        self.beep_check.toggled.connect(self.beep_spin.setEnabled)
        beep_row.addWidget(self.beep_check)
        beep_row.addWidget(self.beep_spin)
        beep_row.addStretch()
        form.addRow("", beep_row)

        self.vad_check = QCheckBox("Voice activity detection (whisper only)")
        self.vad_check.setChecked(settings["vad"])
        self.vad_check.setToolTip("Disable if words at clip edges are missed.")
        form.addRow("", self.vad_check)

        download_row = QHBoxLayout()
        self.download_dir_edit = QLineEdit(settings.get("download_dir", ""))
        self.download_dir_edit.setPlaceholderText(
            str(config.download_dir(settings)))
        download_browse = QPushButton("Browse…")
        download_browse.clicked.connect(self._browse_download_dir)
        download_row.addWidget(self.download_dir_edit, stretch=1)
        download_row.addWidget(download_browse)
        form.addRow("Downloads folder:", download_row)

        cookies_row = QHBoxLayout()
        self.cookies_edit = QLineEdit(settings.get("cookies_file", ""))
        self.cookies_edit.setPlaceholderText(tr("(optional)"))
        self.cookies_edit.setToolTip(
            "Cookie file in Netscape format (as exported by yt-dlp or a "
            "browser extension). Lets downloads access sites that need "
            "your login, e.g. boosty.to. Used for both the format list "
            "and the download itself.")
        cookies_browse = QPushButton("Browse…")
        cookies_browse.clicked.connect(self._browse_cookies)
        cookies_row.addWidget(self.cookies_edit, stretch=1)
        cookies_row.addWidget(cookies_browse)
        form.addRow(tr("Cookies file:"), cookies_row)

        ui_lang_row = QHBoxLayout()
        self.ui_language_combo = QComboBox()
        self.ui_language_combo.addItem("English", "en")
        self.ui_language_combo.addItem("Русский", "ru")
        idx = self.ui_language_combo.findData(
            settings.get("ui_language", "en"))
        self.ui_language_combo.setCurrentIndex(max(idx, 0))
        ui_lang_row.addWidget(self.ui_language_combo)
        ui_lang_row.addWidget(QLabel(tr("(takes effect after restart)")))
        ui_lang_row.addStretch()
        form.addRow(tr("Interface language:"), ui_lang_row)
        layout.addLayout(form)

        layout.addWidget(QLabel(tr("Output location:")))
        self.beside_radio = QRadioButton(
            tr("Next to each input (<name>.clean.<ext>)"))
        self.folder_radio = QRadioButton(tr("Into folder:"))
        folder_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit(settings["output_dir"])
        output_browse = QPushButton("Browse…")
        output_browse.clicked.connect(self._browse_output_dir)
        folder_row.addWidget(self.folder_radio)
        folder_row.addWidget(self.output_dir_edit, stretch=1)
        folder_row.addWidget(output_browse)
        layout.addWidget(self.beside_radio)
        layout.addLayout(folder_row)
        (self.folder_radio if settings["output_mode"] == "folder"
         else self.beside_radio).setChecked(True)
        layout.addStretch()

        self._loading = False
        for signal in (
            self.model_combo.currentTextChanged,
            self.gigaam_combo.currentTextChanged,
            self.device_combo.currentTextChanged,
            self.pad_spin.valueChanged,
            self.language_edit.textChanged,
            self.beep_check.toggled,
            self.beep_spin.valueChanged,
            self.vad_check.toggled,
            self.download_dir_edit.textChanged,
            self.cookies_edit.textChanged,
            self.ui_language_combo.currentIndexChanged,
            self.beside_radio.toggled,
            self.folder_radio.toggled,
            self.output_dir_edit.textChanged,
        ):
            signal.connect(self._apply)

    # ---------------------------------------------------------- browsing
    def _browse_download_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Downloads folder",
                                             self.download_dir_edit.text())
        if d:
            self.download_dir_edit.setText(d)

    def _browse_cookies(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Cookies file", self.cookies_edit.text(),
            "Cookie files (*.txt);;All files (*)")
        if path:
            self.cookies_edit.setText(path)

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder",
                                             self.output_dir_edit.text())
        if d:
            self.output_dir_edit.setText(d)
            self.folder_radio.setChecked(True)

    # ---------------------------------------------------------- persist
    def _apply(self, *_):
        if self._loading:
            return
        self._settings.update({
            "model": self.model_combo.currentText(),
            "gigaam_model": self.gigaam_combo.currentText(),
            "device": self.device_combo.currentText(),
            "pad_ms": self.pad_spin.value(),
            "language": self.language_edit.text().strip() or "ru",
            "vad": self.vad_check.isChecked(),
            "output_mode": ("folder" if self.folder_radio.isChecked()
                            and self.output_dir_edit.text().strip()
                            else "beside"),
            "output_dir": self.output_dir_edit.text().strip(),
            "download_dir": self.download_dir_edit.text().strip(),
            "beep_hz": (self.beep_spin.value()
                        if self.beep_check.isChecked() else 0),
            "ui_language": self.ui_language_combo.currentData(),
            "cookies_file": self.cookies_edit.text().strip(),
        })
        config.save_settings(self._settings)
        self.changed.emit()
