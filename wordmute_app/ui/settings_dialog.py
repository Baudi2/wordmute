"""Settings dialog: models, device, padding, language, VAD, output,
downloads folder."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from ..core import config

WHISPER_MODELS = ["large-v3", "medium", "small", "base"]
GIGAAM_MODELS = ["v3_e2e_rnnt", "v3_e2e_ctc", "v3_rnnt", "v3_ctc"]


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.model_combo = QComboBox()
        self.model_combo.addItems(WHISPER_MODELS)
        if settings["model"] in WHISPER_MODELS:
            self.model_combo.setCurrentText(settings["model"])
        form.addRow("Whisper model:", self.model_combo)

        self.gigaam_combo = QComboBox()
        self.gigaam_combo.addItems(GIGAAM_MODELS)
        if settings["gigaam_model"] in GIGAAM_MODELS:
            self.gigaam_combo.setCurrentText(settings["gigaam_model"])
        form.addRow("GigaAM model:", self.gigaam_combo)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["cuda", "cpu"])
        self.device_combo.setCurrentText(settings["device"])
        form.addRow("Device:", self.device_combo)

        self.pad_spin = QSpinBox()
        self.pad_spin.setRange(0, 1000)
        self.pad_spin.setSingleStep(10)
        self.pad_spin.setSuffix(" ms")
        self.pad_spin.setValue(settings["pad_ms"])
        self.pad_spin.setToolTip("Extra silence around each muted word; "
                                 "never bleeds into neighboring words.")
        form.addRow("Mute padding:", self.pad_spin)

        self.language_edit = QLineEdit(settings["language"])
        self.language_edit.setToolTip("Whisper language code (e.g. ru, en); "
                                      "ignored by GigaAM passes.")
        form.addRow("Whisper language:", self.language_edit)

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
        layout.addLayout(form)

        layout.addWidget(QLabel("Output location:"))
        self.beside_radio = QRadioButton(
            "Next to each input (<name>.clean.<ext>)")
        self.folder_radio = QRadioButton("Into folder:")
        folder_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit(settings["output_dir"])
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output_dir)
        folder_row.addWidget(self.folder_radio)
        folder_row.addWidget(self.output_dir_edit, stretch=1)
        folder_row.addWidget(browse)
        layout.addWidget(self.beside_radio)
        layout.addLayout(folder_row)
        (self.folder_radio if settings["output_mode"] == "folder"
         else self.beside_radio).setChecked(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder",
                                             self.output_dir_edit.text())
        if d:
            self.output_dir_edit.setText(d)
            self.folder_radio.setChecked(True)

    def _browse_download_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Downloads folder",
                                             self.download_dir_edit.text())
        if d:
            self.download_dir_edit.setText(d)

    def values(self) -> dict:
        return {
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
        }
