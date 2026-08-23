"""Settings tab. Changes apply and persist immediately (a transient
"Saved" note confirms); a `changed` signal lets the main window refresh
advice. Settings never affect a run already in progress — options are
captured at Start. Grouped per the design spec: Recognition | Muting
side by side, Files & downloads beneath."""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
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
from .theme import THEMES, apply_theme

WHISPER_MODELS = ["large-v3", "large-v3-turbo", "medium", "small", "base"]
GIGAAM_MODELS = ["v3_e2e_rnnt", "v3_e2e_ctc", "v3_rnnt", "v3_ctc"]
GROUP_WIDTH = 500  # RU labels run ~40% longer than EN


class SettingsTab(QWidget):
    changed = Signal()

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._loading = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(20)

        # ---- Recognition
        recognition = QGroupBox(tr("Recognition"))
        recognition.setMaximumWidth(GROUP_WIDTH)
        rec_form = QFormLayout(recognition)
        rec_form.setVerticalSpacing(12)
        rec_form.setHorizontalSpacing(16)

        self.model_combo = QComboBox()
        self.model_combo.addItems(WHISPER_MODELS)
        if settings["model"] in WHISPER_MODELS:
            self.model_combo.setCurrentText(settings["model"])
        rec_form.addRow(tr("Whisper model:"), self.model_combo)

        self.gigaam_combo = QComboBox()
        self.gigaam_combo.addItems(GIGAAM_MODELS)
        if settings["gigaam_model"] in GIGAAM_MODELS:
            self.gigaam_combo.setCurrentText(settings["gigaam_model"])
        rec_form.addRow(tr("GigaAM model:"), self.gigaam_combo)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["cuda", "cpu"])
        self.device_combo.setCurrentText(settings["device"])
        rec_form.addRow(tr("Device:"), self.device_combo)

        self.language_edit = QLineEdit(settings["language"])
        self.language_edit.setToolTip(
            tr("Whisper language code (e.g. ru, en); ignored by GigaAM "
               "passes."))
        rec_form.addRow(tr("Whisper language:"), self.language_edit)

        self.vad_check = QCheckBox(
            tr("Voice activity detection (whisper only)"))
        self.vad_check.setChecked(settings["vad"])
        self.vad_check.setToolTip(
            tr("Disable if words at clip edges are missed."))
        rec_form.addRow("", self.vad_check)

        self.fast_check = QCheckBox(
            tr("Fast Whisper mode (experimental)"))
        self.fast_check.setChecked(bool(settings.get("fast_mode", False)))
        self.fast_check.setToolTip(
            tr("Batched decoding: 2-4x faster transcription, but a "
               "slightly higher chance of missed words and about twice "
               "the RAM on CPU. Requires voice activity detection."))
        rec_form.addRow("", self.fast_check)

        # ---- Muting
        muting = QGroupBox(tr("Muting"))
        muting.setMaximumWidth(GROUP_WIDTH)
        mute_form = QFormLayout(muting)
        mute_form.setVerticalSpacing(12)
        mute_form.setHorizontalSpacing(16)

        self.pad_spin = QSpinBox()
        self.pad_spin.setRange(0, 1000)
        self.pad_spin.setSingleStep(10)
        self.pad_spin.setValue(settings["pad_ms"])
        self.pad_spin.setToolTip(
            tr("Extra silence around each muted word; never bleeds into "
               "neighboring words."))
        mute_form.addRow(tr("Mute padding:"), self.pad_spin)

        # design v3: checkbox gets its own full-width row, the frequency
        # its own labeled row beneath (enabled only when checked)
        self.beep_check = QCheckBox(tr("Beep instead of silence"))
        self.beep_check.setChecked(bool(settings.get("beep_hz", 0)))
        self.beep_check.setToolTip(
            tr("Replace muted words with a beep tone instead of silence. "
               "Note: files with several audio tracks keep only the "
               "first one in beep mode."))
        mute_form.addRow(self.beep_check)
        self.beep_spin = QSpinBox()
        self.beep_spin.setRange(200, 4000)
        self.beep_spin.setSingleStep(100)
        self.beep_spin.setValue(settings.get("beep_hz", 0) or 1000)
        self.beep_spin.setEnabled(self.beep_check.isChecked())
        self.beep_check.toggled.connect(self.beep_spin.setEnabled)
        mute_form.addRow(tr("Frequency:"), self.beep_spin)

        top_row = QHBoxLayout()
        top_row.setSpacing(20)
        top_row.addWidget(recognition)
        top_row.addWidget(muting)
        top_row.addStretch()
        outer.addLayout(top_row)

        # ---- Files & downloads
        files_box = QGroupBox(tr("Files && downloads"))
        files_box.setMaximumWidth(GROUP_WIDTH * 2 + 20)
        files_form = QFormLayout(files_box)
        files_form.setVerticalSpacing(12)
        files_form.setHorizontalSpacing(16)

        download_row = QHBoxLayout()
        self.download_dir_edit = QLineEdit(settings.get("download_dir", ""))
        self.download_dir_edit.setPlaceholderText(
            str(config.download_dir(settings)))
        download_browse = QPushButton(tr("Browse…"))
        download_browse.clicked.connect(self._browse_download_dir)
        download_row.addWidget(self.download_dir_edit, stretch=1)
        download_row.addWidget(download_browse)
        files_form.addRow(tr("Downloads folder:"), download_row)

        cookies_row = QHBoxLayout()
        self.cookies_edit = QLineEdit(settings.get("cookies_file", ""))
        self.cookies_edit.setPlaceholderText(tr("(optional)"))
        self.cookies_edit.setToolTip(
            tr("Cookie file in Netscape format (as exported by yt-dlp or "
               "a browser extension)."))
        cookies_browse = QPushButton(tr("Browse…"))
        cookies_browse.clicked.connect(self._browse_cookies)
        cookies_row.addWidget(self.cookies_edit, stretch=1)
        cookies_row.addWidget(cookies_browse)
        files_form.addRow(tr("Cookies file:"), cookies_row)
        cookies_hint = QLabel(tr(
            "Used for members-only downloads (e.g. Boosty) — exported "
            "from your browser."))
        cookies_hint.setProperty("muted", True)
        cookies_hint.setWordWrap(True)
        files_form.addRow("", cookies_hint)

        output_col = QVBoxLayout()
        self.beside_radio = QRadioButton(
            tr("Next to each input (<name>.clean.<ext>)"))
        self.folder_radio = QRadioButton(tr("Into folder:"))
        folder_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit(settings["output_dir"])
        output_browse = QPushButton(tr("Browse…"))
        output_browse.clicked.connect(self._browse_output_dir)
        folder_row.addWidget(self.folder_radio)
        folder_row.addWidget(self.output_dir_edit, stretch=1)
        folder_row.addWidget(output_browse)
        output_col.addWidget(self.beside_radio)
        output_col.addLayout(folder_row)
        (self.folder_radio if settings["output_mode"] == "folder"
         else self.beside_radio).setChecked(True)
        files_form.addRow(tr("Output location:"), output_col)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("Dark"), "dark")
        self.theme_combo.addItem(tr("Light"), "light")
        idx = self.theme_combo.findData(settings.get("theme", "dark"))
        self.theme_combo.setCurrentIndex(max(idx, 0))
        files_form.addRow(tr("Theme:"), self.theme_combo)

        ui_lang_row = QHBoxLayout()
        self.ui_language_combo = QComboBox()
        self.ui_language_combo.addItem("English", "en")
        self.ui_language_combo.addItem("Русский", "ru")
        idx = self.ui_language_combo.findData(
            settings.get("ui_language", "en"))
        self.ui_language_combo.setCurrentIndex(max(idx, 0))
        ui_lang_row.addWidget(self.ui_language_combo)
        restart_note = QLabel(tr("(takes effect after restart)"))
        restart_note.setProperty("muted", True)
        ui_lang_row.addWidget(restart_note)
        ui_lang_row.addStretch()
        files_form.addRow(tr("Interface language:"), ui_lang_row)
        outer.addWidget(files_box)

        self.saved_label = QLabel("")
        self.saved_label.setProperty("muted", True)
        outer.addWidget(self.saved_label)
        outer.addStretch()

        self._saved_timer = QTimer(self)
        self._saved_timer.setSingleShot(True)
        self._saved_timer.setInterval(1800)
        self._saved_timer.timeout.connect(
            lambda: self.saved_label.setText(""))

        self.retranslate_ui()
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
            self.theme_combo.currentIndexChanged,
            self.beside_radio.toggled,
            self.folder_radio.toggled,
            self.output_dir_edit.textChanged,
        ):
            signal.connect(self._apply)

    def reload(self):
        """Re-read the fields another writer shares with us (the
        component wizard picks model/device/language into the same
        dict): the widgets must follow, or the next keystroke here
        writes their stale values back over the wizard's choice."""
        self._loading = True
        try:
            s = self._settings
            if s.get("model") in WHISPER_MODELS:
                self.model_combo.setCurrentText(s["model"])
            if s.get("gigaam_model") in GIGAAM_MODELS:
                self.gigaam_combo.setCurrentText(s["gigaam_model"])
            if s.get("device") in ("cuda", "cpu"):
                self.device_combo.setCurrentText(s["device"])
            index = self.ui_language_combo.findData(s.get("ui_language"))
            if index >= 0:
                self.ui_language_combo.setCurrentIndex(index)
        finally:
            self._loading = False

    def retranslate_ui(self):
        """Unit suffixes belong here, never in the constructor: set once
        at build time they survive a language switch as «100 ms» in a
        Russian window. NBSP keeps value and unit on one line, and the
        group separator is off so 1000 Hz is not «1 000 Гц»."""
        self.pad_spin.setSuffix("\u00A0" + tr("ms"))
        self.pad_spin.setGroupSeparatorShown(False)
        self.beep_spin.setSuffix("\u00A0" + tr("Hz"))
        self.beep_spin.setGroupSeparatorShown(False)

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
        old_theme = self._settings.get("theme", "dark")
        self._settings.update({
            "model": self.model_combo.currentText(),
            "gigaam_model": self.gigaam_combo.currentText(),
            "device": self.device_combo.currentText(),
            "pad_ms": self.pad_spin.value(),
            "language": self.language_edit.text().strip() or "ru",
            "vad": self.vad_check.isChecked(),
            "fast_mode": self.fast_check.isChecked(),
            "output_mode": ("folder" if self.folder_radio.isChecked()
                            and self.output_dir_edit.text().strip()
                            else "beside"),
            "output_dir": self.output_dir_edit.text().strip(),
            "download_dir": self.download_dir_edit.text().strip(),
            "beep_hz": (self.beep_spin.value()
                        if self.beep_check.isChecked() else 0),
            "ui_language": self.ui_language_combo.currentData(),
            "theme": self.theme_combo.currentData(),
            "cookies_file": self.cookies_edit.text().strip(),
        })
        config.save_settings(self._settings)
        new_theme = self._settings.get("theme", "dark")
        if new_theme != old_theme and new_theme in THEMES:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                apply_theme(app, new_theme)
        self.saved_label.setText(tr("Saved"))
        self._saved_timer.start()
        self.changed.emit()
