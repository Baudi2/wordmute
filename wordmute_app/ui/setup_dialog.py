"""First-run setup wizard (slim installer): one component per step,
then a single install pass that leaves NOTHING to download later —
model weights included, so the first video never stops for a 3 GB
surprise. Also serves as the component manager from the Models tab.

Design: deliverables/setup-wizard-handoff.md (8 steps, объект-имена в
wordmute-setup.qss). Deviations from the handoff, deliberate:
  * i18n uses the app's own tr() dict + set_language(), not
    QTranslator/.qm — the language button retranslates by rebuilding
    the pages while preserving every selection;
  * state lives in the app's settings.json, not QSettings;
  * ffmpeg is REQUIRED (nothing can be muted without it), not
    optional-on-by-default.
"""

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core import config, gpu, models, runtime_env
from .i18n import current_language, set_language, tr

STEP_KEYS = ("intro", "python", "whisper", "ytdlp", "ffmpeg", "gigaam",
             "review", "install")
STEP_NAMES = {
    "intro": "What you need", "python": "Python", "whisper": "Whisper",
    "ytdlp": "yt-dlp", "ffmpeg": "ffmpeg", "gigaam": "GigaAM",
    "review": "Review", "install": "Installing",
}

MODEL_CHOICES = (
    ("large-v3", "large-v3", "best quality"),
    ("large-v3-turbo", "large-v3-turbo", "almost large-v3, much faster"),
    ("medium", "medium", "good compromise"),
    ("small", "small", "fastest, lower accuracy"),
)

PYTHON_MB = 30
YTDLP_MB = 10
FFMPEG_MB = 80
GIGAAM_PKG_MB = 60
WHISPER_GPU_MB = 1600
WHISPER_CPU_MB = 300


def fmt_mb(mb: int) -> str:
    """'≈1,6 ГБ' / '≈80 МБ' — comma decimal in RU, dot in EN."""
    if mb >= 1000:
        text = f"{mb / 1000:.1f}"
        if tr("GB") == "ГБ":
            text = text.replace(".", ",")
        return f"≈{text} {tr('GB')}"
    return f"≈{mb} {tr('MB')}"


class SetupWorker(QThread):
    log_line = Signal(str)
    stage = Signal(str)
    step_done = Signal(str, bool)      # stage name, ok
    progress = Signal(int, int)        # done, total bytes (0 = unknown)
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
                self.step_done.emit(name, True)
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
        runtime_env.install_packages(packages, log=log, cancelled=cancelled)
    return step


class SelectCard(QFrame):
    """Clickable card wrapping a checkbox/radio (the control stays
    visible for keyboard use); repaints via the selected property."""

    def __init__(self, control, title: str, hint: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("selectCard", True)
        self.setMinimumHeight(44)
        self.control = control
        control.setText("")          # the card owns the label
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)
        row.addWidget(control, alignment=Qt.AlignTop)
        control.setVisible(True)     # hidden while detached (rebuilds)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("card_option_title")
        text.addWidget(self.title_label)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("card_option_hint")
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))
        text.addWidget(self.hint_label)
        row.addLayout(text, stretch=1)
        control.toggled.connect(self._sync)
        self._sync(control.isChecked())

    def mousePressEvent(self, event):
        if self.control.isEnabled():
            self.control.click()
        super().mousePressEvent(event)

    def _sync(self, on: bool):
        if self.property("selected") == on:
            return
        self.setProperty("selected", on)
        self.style().unpolish(self)
        self.style().polish(self)


class SetupDialog(QDialog):
    def __init__(self, parent=None, first_run: bool = True):
        super().__init__(parent)
        self.setObjectName("setup_wizard")
        self.setWindowTitle(tr("WordMute components"))
        self.setModal(True)
        self.resize(920, 620)
        self.setMinimumSize(820, 560)
        self._first_run = first_run
        self._worker = None
        self._done = False
        self._settings = config.load_settings()
        self._status = runtime_env.status()
        self._gpus = gpu.detect_gpus()
        self._rows = {}          # component key -> install row widgets
        self._step = 0
        self._steps = list(STEP_KEYS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_step_strip())
        self.pages = QStackedWidget()
        self.pages.setObjectName("wizard_pages")
        root.addWidget(self.pages, stretch=1)
        root.addWidget(self._build_footer())

        self._build_state()
        self._build_pages()
        self.set_step(0)

    # ------------------------------------------------------------ chrome
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("wizard_header")
        header.setFixedHeight(56)
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 0, 20, 0)
        row.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("wizard_logo")
        from .theme import app_icon
        logo.setPixmap(app_icon().pixmap(QSize(26, 26)))
        row.addWidget(logo)
        brand = QLabel("WordMute")
        brand.setObjectName("wizard_brand")
        row.addWidget(brand)
        self.brand_sub = QLabel(tr("component setup"))
        self.brand_sub.setObjectName("wizard_brand_sub")
        row.addWidget(self.brand_sub)
        row.addStretch()
        self.lang_button = QToolButton()
        self.lang_button.setObjectName("lang_button")
        self.lang_button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.lang_button)
        menu.setObjectName("lang_menu")
        for code, native in (("ru", "Русский"), ("en", "English")):
            act = menu.addAction(native)
            act.setCheckable(True)
            act.setChecked(current_language() == code)
            act.triggered.connect(
                lambda _=False, c=code: self._set_language(c))
        self.lang_button.setMenu(menu)
        self._sync_lang_button()
        row.addWidget(self.lang_button)
        return header

    def _build_step_strip(self) -> QWidget:
        strip = QWidget()
        strip.setObjectName("step_strip")
        box = QVBoxLayout(strip)
        box.setContentsMargins(24, 14, 24, 16)
        box.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.step_counter = QLabel()
        self.step_counter.setObjectName("step_counter")
        top.addWidget(self.step_counter)
        self.step_chip = QLabel()
        self.step_chip.setObjectName("step_chip")
        top.addWidget(self.step_chip)
        top.addStretch()
        self.step_remaining = QLabel()
        self.step_remaining.setObjectName("step_remaining")
        top.addWidget(self.step_remaining)
        box.addLayout(top)
        rail = QWidget()
        rail.setObjectName("step_rail")
        rail_row = QHBoxLayout(rail)
        rail_row.setContentsMargins(0, 0, 0, 0)
        rail_row.setSpacing(5)
        self._rail_segments = []
        for index, key in enumerate(self._steps):
            seg = QFrame()
            seg.setProperty("railSeg", True)
            seg.setFixedHeight(4)
            seg.setToolTip(tr(STEP_NAMES[key]))
            seg.setCursor(Qt.PointingHandCursor)
            seg.mousePressEvent = (
                lambda _e, i=index: self._rail_clicked(i))
            rail_row.addWidget(seg, stretch=1)
            self._rail_segments.append(seg)
        box.addWidget(rail)
        return strip

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("wizard_footer")
        footer.setFixedHeight(64)
        row = QHBoxLayout(footer)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(9)
        self.btn_cancel = QPushButton(tr("Cancel"))
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.clicked.connect(self._cancel_clicked)
        row.addWidget(self.btn_cancel)
        row.addStretch()
        self.btn_back = QPushButton(tr("Back"))
        self.btn_back.setObjectName("btn_back")
        self.btn_back.clicked.connect(
            lambda: self.set_step(self._step - 1))
        row.addWidget(self.btn_back)
        self.btn_next = QPushButton(tr("Next"))
        self.btn_next.setObjectName("btn_next")
        self.btn_next.setProperty("primary", True)
        self.btn_next.clicked.connect(self._next_clicked)
        row.addWidget(self.btn_next)
        return footer

    # ------------------------------------------------------------- state
    def _build_state(self):
        """Controls live outside the pages so a language rebuild keeps
        every selection (and so tests can poke them directly)."""
        s, st = self._settings, self._status
        self.whisper_check = QCheckBox(tr("Install"))
        self.whisper_check.setChecked(not st["faster_whisper"])
        self.whisper_check.setEnabled(not st["faster_whisper"])
        self.ytdlp_check = QCheckBox(tr("Install"))
        self.ytdlp_check.setChecked(not st["yt_dlp"])
        self.ytdlp_check.setEnabled(not st["yt_dlp"])
        self.ffmpeg_check = QCheckBox(tr("Install"))
        self.ffmpeg_check.setChecked(not st["ffmpeg"])
        self.ffmpeg_check.setEnabled(not st["ffmpeg"])
        self.gigaam_check = QCheckBox(tr("Install"))
        self.gigaam_check.setChecked(False)

        self.device_group = QButtonGroup(self)
        self.gpu_radio = QRadioButton(tr("GPU (NVIDIA)"))
        self.cpu_radio = QRadioButton(tr("CPU only"))
        for radio in (self.gpu_radio, self.cpu_radio):
            self.device_group.addButton(radio)
        (self.gpu_radio if self._gpus else self.cpu_radio).setChecked(True)

        self.model_group = QButtonGroup(self)
        self.model_radios = {}
        current = s.get("model", "large-v3")
        for name, _label, _hint in MODEL_CHOICES:
            radio = QRadioButton(name)
            radio.setChecked(name == current)
            self.model_group.addButton(radio)
            self.model_radios[name] = radio
        if not any(r.isChecked() for r in self.model_radios.values()):
            self.model_radios["large-v3"].setChecked(True)

    def selected_model(self) -> str:
        for name, radio in self.model_radios.items():
            if radio.isChecked():
                return name
        return "large-v3"

    def _whisper_mb(self) -> int:
        return (WHISPER_GPU_MB if self.gpu_radio.isChecked()
                else WHISPER_CPU_MB)

    def _plan(self) -> list:
        """[(key, label, size_mb, selected)] — drives review + install."""
        st = self._status
        model = self.selected_model()
        model_mb = runtime_env.WHISPER_SIZE_MB.get(model, 3000)
        need_python = (not (st["python"] and st["pip"])
                       and (self.whisper_check.isChecked()
                            or self.ytdlp_check.isChecked()
                            or self.gigaam_check.isChecked()))
        rows = [
            ("python", tr("Python runtime"), PYTHON_MB, need_python),
            ("whisper", "Whisper", self._whisper_mb(),
             self.whisper_check.isChecked()),
            ("whisper_model", tr("Recognition model {}").format(model),
             model_mb, self.whisper_check.isChecked()
             or not st["faster_whisper"]),
            ("ytdlp", "yt-dlp", YTDLP_MB, self.ytdlp_check.isChecked()),
            ("ffmpeg", "ffmpeg", FFMPEG_MB, self.ffmpeg_check.isChecked()),
            ("gigaam", "GigaAM",
             GIGAAM_PKG_MB + runtime_env.GIGAAM_ONNX_SIZE_MB,
             self.gigaam_check.isChecked()),
        ]
        return rows

    def total_mb(self) -> int:
        return sum(mb for _k, _l, mb, on in self._plan() if on)

    # ------------------------------------------------------------- pages
    def _persistent_controls(self):
        return (self.whisper_check, self.ytdlp_check, self.ffmpeg_check,
                self.gigaam_check, self.gpu_radio, self.cpu_radio,
                *self.model_radios.values())

    def _build_pages(self):
        # the pages REPARENT these controls into their cards, so a page
        # rebuild (language switch) would delete them along with the old
        # page — take them back first, then drop the old pages
        for control in self._persistent_controls():
            control.setParent(self)
            control.hide()   # required components have no card at all
        while self.pages.count():
            page = self.pages.widget(0)
            self.pages.removeWidget(page)
            page.deleteLater()
        for key in self._steps:
            self.pages.addWidget(self._make_page(key))

    def _page_shell(self):
        scroll = QScrollArea()
        scroll.setObjectName("page_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        box = QVBoxLayout(body)
        box.setContentsMargins(24, 22, 24, 20)
        box.setSpacing(14)
        scroll.setWidget(body)
        return scroll, box

    def _head(self, box, name, sub, size_mb=None, required=None):
        row = QHBoxLayout()
        row.setSpacing(8)
        title = QLabel(name)
        title.setObjectName("comp_name")
        row.addWidget(title)
        if required is not None:
            badge = QLabel(tr("required") if required else tr("optional"))
            badge.setProperty("badge",
                              "required" if required else "optional")
            row.addWidget(badge)
        row.addStretch()
        if size_mb is not None:
            size = QLabel(fmt_mb(size_mb))
            size.setObjectName("comp_size")
            row.addWidget(size)
        box.addLayout(row)
        if sub:
            sub_label = QLabel(sub)
            sub_label.setObjectName("comp_sub")
            sub_label.setWordWrap(True)
            box.addWidget(sub_label)
        rule = QFrame()
        rule.setObjectName("page_rule")
        rule.setFixedHeight(1)
        box.addWidget(rule)

    def _lead(self, box, text):
        label = QLabel(text)
        label.setObjectName("page_lead")
        label.setWordWrap(True)
        label.setMaximumWidth(660)
        box.addWidget(label)

    def _bullets(self, box, items):
        for text in items:
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel("•")
            dot.setObjectName("bullet_dot")
            row.addWidget(dot, alignment=Qt.AlignTop)
            label = QLabel(text)
            label.setObjectName("bullet_text")
            label.setProperty("muted", True)
            label.setWordWrap(True)
            row.addWidget(label, stretch=1)
            box.addLayout(row)

    def _note(self, box, text, severity="info"):
        row = QHBoxLayout()
        row.setSpacing(8)
        icon = QLabel("⚠" if severity != "info" else "ℹ")
        icon.setObjectName("page_note_icon")
        row.addWidget(icon, alignment=Qt.AlignTop)
        label = QLabel(text)
        label.setObjectName("page_note")
        label.setProperty("severity", severity)
        label.setWordWrap(True)
        row.addWidget(label, stretch=1)
        box.addLayout(row)
        return label

    def _make_page(self, key):
        scroll, box = self._page_shell()
        builder = getattr(self, f"_page_{key}")
        builder(box)
        box.addStretch()
        return scroll

    def _page_intro(self, box):
        self._head(box, tr("What you need"), "", None, None)
        self._lead(box, tr(
            "WordMute installs the app itself; the recognition engines "
            "are downloaded once, right now. Everything lands in your "
            "user folder — no administrator rights needed."))
        self._bullets(box, [
            tr("A stable internet connection and free disk space."),
            tr("In Russia python.org / PyPI / Hugging Face may be "
               "blocked or throttled — turn on a VPN for the setup."),
            tr("The download can be interrupted and resumed: already "
               "downloaded parts are kept."),
        ])
        self._note(box, tr("After this setup the app works fully "
                           "offline — nothing downloads mid-video."))

    def _page_python(self, box):
        self._head(box, tr("Python runtime"),
                   tr("Isolated interpreter for the engines"),
                   PYTHON_MB, True)
        self._lead(box, tr(
            "An embeddable Python build plus pip, installed only for "
            "WordMute. Your system Python (if any) is not touched."))
        if self._status["python"] and self._status["pip"]:
            self._note(box, tr("Already installed — this step will be "
                               "skipped."))

    def _page_whisper(self, box):
        self._head(box, "Whisper", tr("Speech recognition engine"),
                   self._whisper_mb(), True)
        self._lead(box, tr(
            "faster-whisper handles any language and runs right after "
            "setup. Pick how it should run and which model to fetch."))
        label = QLabel(tr("Device"))
        label.setObjectName("section_label")
        box.addWidget(label)
        device_row = QHBoxLayout()
        device_row.setSpacing(8)
        device_row.addWidget(SelectCard(
            self.gpu_radio, tr("GPU (NVIDIA)"),
            tr("Fast. Requires an NVIDIA card ({} download).")
            .format(fmt_mb(WHISPER_GPU_MB))))
        device_row.addWidget(SelectCard(
            self.cpu_radio, tr("CPU only"),
            tr("Works everywhere, slower ({} download).")
            .format(fmt_mb(WHISPER_CPU_MB))))
        box.addLayout(device_row)
        if not self._gpus:
            self._note(box, tr("No NVIDIA GPU detected — CPU is "
                               "preselected."))
        label = QLabel(tr("Recognition model"))
        label.setObjectName("section_label")
        box.addWidget(label)
        sub = QLabel(tr("Downloaded during this setup, so the first "
                        "video starts immediately."))
        sub.setObjectName("page_sub")
        sub.setWordWrap(True)
        box.addWidget(sub)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (name, _label, hint) in enumerate(MODEL_CHOICES):
            size = runtime_env.WHISPER_SIZE_MB.get(name, 0)
            card = SelectCard(self.model_radios[name], name,
                              f"{tr(hint)} · {fmt_mb(size)}")
            grid.addWidget(card, i // 2, i % 2)
        box.addLayout(grid)

    def _page_ytdlp(self, box):
        self._head(box, "yt-dlp", tr("Download videos by link"),
                   YTDLP_MB, False)
        self._lead(box, tr(
            "Lets you paste a link (YouTube, VK, rutube, Boosty…) "
            "instead of picking a local file. Tiny download."))
        box.addWidget(SelectCard(
            self.ytdlp_check, tr("Install yt-dlp"),
            tr("Without it, only local files can be processed.")))

    def _page_ffmpeg(self, box):
        self._head(box, "ffmpeg", tr("Audio and video processing"),
                   FFMPEG_MB, True)
        self._lead(box, tr(
            "Does the actual muting and audio extraction. WordMute "
            "cannot process anything without it."))
        box.addWidget(SelectCard(
            self.ffmpeg_check, tr("Install ffmpeg"),
            tr("Required — muting is impossible without ffmpeg.")))

    def _page_gigaam(self, box):
        total = GIGAAM_PKG_MB + runtime_env.GIGAAM_ONNX_SIZE_MB
        self._head(box, "GigaAM", tr("Better Russian recognition"),
                   total, False)
        self._lead(box, tr(
            "An optional second engine that is noticeably more "
            "accurate on Russian speech. Runs fast even without a "
            "graphics card and needs no accounts."))
        self._bullets(box, [
            tr("Engine and model are downloaded now — nothing is left "
               "for the first video."),
            tr("Experimental: use it together with Whisper, not "
               "instead of it."),
        ])
        box.addWidget(SelectCard(
            self.gigaam_check, tr("Install GigaAM"),
            tr("{} including the model").format(fmt_mb(total))))

    def _page_review(self, box):
        self._head(box, tr("Review"), tr("What will be downloaded now"),
                   None, None)
        self.review_box = QVBoxLayout()
        self.review_box.setSpacing(6)
        box.addLayout(self.review_box)
        self.review_total = QLabel()
        self.review_total.setObjectName("review_total_value")
        box.addWidget(self.review_total)
        folder = QLabel(tr("Install folder: {}").format(
            runtime_env.runtime_dir()))
        folder.setObjectName("folder_path")
        folder.setWordWrap(True)
        box.addWidget(folder)

    def _refresh_review(self):
        while self.review_box.count():
            item = self.review_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for _key, label, mb, on in self._plan():
            row = QFrame()
            row.setProperty("reviewRow", True)
            line = QHBoxLayout(row)
            line.setContentsMargins(10, 6, 10, 6)
            name = QLabel(label)
            name.setObjectName("review_name")
            line.addWidget(name)
            line.addStretch()
            size = QLabel(fmt_mb(mb) if on else tr("skipped"))
            size.setObjectName("review_size")
            if not on:
                size.setProperty("muted", True)
            line.addWidget(size)
            self.review_box.addWidget(row)
        self.review_total.setText(
            tr("Total download: {}").format(fmt_mb(self.total_mb())))

    def _page_install(self, box):
        title = QLabel(tr("Installing"))
        title.setObjectName("install_title")
        box.addWidget(title)
        self.install_sub = QLabel(tr("Do not close the window."))
        self.install_sub.setObjectName("install_sub")
        self.install_sub.setWordWrap(True)
        box.addWidget(self.install_sub)
        self.total_progress = QProgressBar()
        self.total_progress.setObjectName("total_progress")
        self.total_progress.setRange(0, 0)
        box.addWidget(self.total_progress)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(4)
        box.addLayout(self.rows_box)
        self.log_toggle = QPushButton(tr("Details"))
        self.log_toggle.setObjectName("log_toggle")
        self.log_toggle.setCheckable(True)
        box.addWidget(self.log_toggle, alignment=Qt.AlignLeft)
        self.log = QPlainTextEdit()
        self.log.setObjectName("setup_log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setVisible(False)
        self.log_toggle.toggled.connect(self.log.setVisible)
        box.addWidget(self.log, stretch=1)
        self.install_note = self._note(box, "", "info")
        self.install_note.parentWidget()
        self.install_note.setVisible(False)

    def _refresh_install_rows(self):
        while self.rows_box.count():
            item = self.rows_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows = {}
        for key, label, _mb, on in self._plan():
            row = QFrame()
            row.setProperty("installRow", True)
            row.setProperty("state", "todo" if on else "skipped")
            line = QHBoxLayout(row)
            line.setContentsMargins(10, 6, 10, 6)
            line.setSpacing(8)
            icon = QLabel("•")
            icon.setObjectName("row_icon")
            line.addWidget(icon)
            name = QLabel(label)
            name.setObjectName("row_name")
            line.addWidget(name)
            line.addStretch()
            state = QLabel(tr("waiting") if on else tr("skipped"))
            state.setObjectName("row_state")
            line.addWidget(state)
            self.rows_box.addWidget(row)
            self._rows[key] = (row, icon, state)

    def _set_row_state(self, key: str, state: str, text: str):
        entry = self._rows.get(key)
        if not entry:
            return
        row, icon, label = entry
        row.setProperty("state", state)
        row.style().unpolish(row)
        row.style().polish(row)
        icon.setText({"done": "✓", "err": "✕", "run": "›"}.get(state, "•"))
        label.setText(text)

    # -------------------------------------------------------- navigation
    def set_step(self, index: int):
        index = max(0, min(index, len(self._steps) - 1))
        self._step = index
        self.pages.setCurrentIndex(index)
        key = self._steps[index]
        if key == "review":
            self._refresh_review()
        total = len(self._steps)
        self.step_counter.setText(
            tr("Step {} of {}").format(index + 1, total))
        self.step_chip.setText(tr(STEP_NAMES[key]))
        left = total - 1 - index
        self.step_remaining.setText(
            tr("last step") if left <= 0 else tr("{} left").format(left))
        for i, seg in enumerate(self._rail_segments):
            state = ("current" if i == index
                     else "done" if i < index else "todo")
            seg.setProperty("state", state)
            seg.style().unpolish(seg)
            seg.style().polish(seg)
        installing = key == "install"
        self.btn_back.setVisible(not installing)
        self.btn_back.setEnabled(index > 0)
        self.btn_next.setText(
            tr("Install") if key == "review"
            else tr("Start working") if self._done
            else tr("Abort") if installing else tr("Next"))
        self.btn_next.setProperty("danger", installing and not self._done)
        self.btn_next.style().unpolish(self.btn_next)
        self.btn_next.style().polish(self.btn_next)
        self.btn_cancel.setVisible(not installing)

    def _rail_clicked(self, index: int):
        if index < self._step and self._steps[self._step] != "install":
            self.set_step(index)

    def _next_clicked(self):
        key = self._steps[self._step]
        if key == "review":
            self.set_step(self._step + 1)
            self._install()
        elif key == "install":
            if self._done:
                self.accept()
            else:
                self._cancel_clicked()
        else:
            self.set_step(self._step + 1)

    def _set_language(self, code: str):
        # compare against the ACTIVE language, not the stored setting:
        # the two can differ (settings written before the UI applied
        # them), and then the button would silently do nothing
        if current_language() == code:
            return
        set_language(code)
        self._settings["ui_language"] = code
        config.save_settings(self._settings)
        self._sync_lang_button()
        self._retranslate()

    def _sync_lang_button(self):
        code = current_language()
        self.lang_button.setText("RU" if code == "ru" else "EN")
        for act in self.lang_button.menu().actions():
            act.setChecked(act.text() == ("Русский" if code == "ru"
                                          else "English"))

    def _retranslate(self):
        """Rebuild the pages (our i18n is a dict, not QTranslator);
        every selection survives because the controls live outside."""
        self.setWindowTitle(tr("WordMute components"))
        self.brand_sub.setText(tr("component setup"))
        self.btn_cancel.setText(tr("Cancel"))
        self.btn_back.setText(tr("Back"))
        for seg, key in zip(self._rail_segments, self._steps):
            seg.setToolTip(tr(STEP_NAMES[key]))
        self._build_pages()
        self.set_step(self._step)

    # ---------------------------------------------------------- install
    def _build_steps(self):
        """[(stage key, callable)] for the worker, in download order."""
        st = runtime_env.status()
        steps = []
        model = self.selected_model()
        need_python = ((self.whisper_check.isChecked()
                        or self.ytdlp_check.isChecked()
                        or self.gigaam_check.isChecked())
                       and not (st["python"] and st["pip"]))
        if need_python:
            steps.append(("python", _wrap(runtime_env.install_python)))
        if self.ffmpeg_check.isChecked():
            steps.append(("ffmpeg", _wrap(runtime_env.install_ffmpeg)))
        packages = []
        if self.whisper_check.isChecked():
            flavor = ("whisper_gpu" if self.gpu_radio.isChecked()
                      else "whisper_cpu")
            packages += runtime_env.COMPONENTS[flavor]["packages"]
        if self.ytdlp_check.isChecked():
            packages += runtime_env.COMPONENTS["ytdlp"]["packages"]
        if packages:
            steps.append(("whisper", _packages_step(packages)))
        # model weights download HERE, not on the first video
        if self.whisper_check.isChecked() or not st["faster_whisper"]:
            steps.append(("whisper_model",
                          _wrap(runtime_env.install_whisper_model,
                                model_name=model)))
        if self.gigaam_check.isChecked():
            steps.append(("gigaam", _packages_step(
                runtime_env.COMPONENTS["gigaam"]["packages"])))
            steps.append(("gigaam_model",
                          _wrap(runtime_env.install_gigaam_model,
                                model_name=self._settings.get(
                                    "gigaam_model", "v3_rnnt"))))
        return steps

    def _install(self):
        self._refresh_install_rows()
        steps = self._build_steps()
        if not steps:
            self._on_finished(True, "")
            return
        self._save_choices()
        self.total_progress.setRange(0, 0)
        self._worker = SetupWorker(steps)
        self._worker.log_line.connect(self.log.appendPlainText)
        self._worker.stage.connect(self._on_stage)
        self._worker.step_done.connect(
            lambda key, ok: self._set_row_state(
                key if key in self._rows else "gigaam", "done",
                tr("done")))
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.start()

    def _on_stage(self, key: str):
        row_key = key if key in self._rows else "gigaam"
        self._set_row_state(row_key, "run", tr("downloading…"))
        self.install_sub.setText(tr("Installing: {}").format(key))

    def _on_progress(self, done: int, total: int):
        if total:
            self.total_progress.setRange(0, 100)
            self.total_progress.setValue(int(done / total * 100))
        else:
            self.total_progress.setRange(0, 0)

    def _on_finished(self, ok: bool, message: str):
        self._worker = None
        if ok:
            runtime_env.activate()
            self._done = True
            self.total_progress.setRange(0, 100)
            self.total_progress.setValue(100)
            self.install_sub.setText(
                tr("Done — everything is installed and ready."))
            self.install_note.setVisible(False)
        else:
            self.install_note.setText(
                tr("Setup failed: {}").format(message))
            self.install_note.setProperty("severity", "error")
            self.install_note.setVisible(True)
            self.log.appendPlainText(message)
            for key, entry in self._rows.items():
                if entry[2].text() == tr("downloading…"):
                    self._set_row_state(key, "err", tr("failed"))
        self.set_step(self._step)

    def _save_choices(self):
        changed = False
        model = self.selected_model()
        if self._settings.get("model") != model:
            self._settings["model"] = model
            changed = True
        device = "cuda" if self.gpu_radio.isChecked() else "cpu"
        if self._settings.get("device") != device:
            self._settings["device"] = device
            changed = True
        if changed:
            config.save_settings(self._settings)

    # --------------------------------------------------------- lifecycle
    def accept(self):
        self._save_choices()
        super().accept()

    def _cancel_clicked(self):
        if self._worker is not None:
            if QMessageBox.question(
                    self, "WordMute",
                    tr("Stop the installation? Downloaded parts are "
                       "kept and setup resumes next time.")) \
                    != QMessageBox.StandardButton.Yes:
                return
            self._worker.cancel()
            self.install_sub.setText(tr("Cancelling…"))
            return
        (self.accept if self._done else self.reject)()

    def closeEvent(self, event):
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(30000)
        event.accept()
