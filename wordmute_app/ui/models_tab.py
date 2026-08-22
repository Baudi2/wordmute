"""Models tab — three groups (design models-tab-handoff.md, mock 5a):

  Устройство            what the recognition runs on, with a way out
                        of CPU mode instead of a dead-end warning
  Модели распознавания  ONE list for Whisper and GigaAM, catalogue
                        sizes before download, in-row progress, ⋯ menu
                        instead of red buttons, disk usage as a bar
  Обслуживание          updates as a list of rows with states, one
                        button that morphs «Проверить» → «Обновить все
                        (N)», the wizard re-entry and the repair link

Nothing here is a QTableWidget any more: rows are small frames, so the
sheet can style states (busy / err / new) per row.
"""

import subprocess
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core import config, gpu, models, runtime_env, updates
from ..core.proc import creationflags
from .. import __version__
from .dialogs import confirm, inform, mark_danger, repolish, themed_menu
from .elided_label import ElidedLabel
from .formats import fmt_bytes, human_datetime
from .i18n import tr
from .theme import ui_icon
from .threads import start_thread, wait_thread

WHISPER_MODELS = ("large-v3", "large-v3-turbo", "medium", "small", "base")
GIGAAM_KEY = "gigaam"
ACCENT = "#9184d9"
ACCENT_TEXT = "#d2cefd"
MUTED = "#9397ab"
ERROR_TEXT = "#eab7b7"





# ================================================================ workers
class WhisperDownloadWorker(QThread):
    """snapshot_download in a SUBPROCESS so «Отменить» can kill it —
    huggingface_hub cannot be interrupted inside a thread. Partial
    blobs stay in the hub cache and resume on the next try."""
    finished_ok = Signal(str, bool, str)     # model, ok, message

    def __init__(self, model: str, parent=None):
        super().__init__(parent)
        self._model = model
        self._proc = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                pass

    def run(self):
        try:
            self._proc = subprocess.Popen(
                models.snapshot_download_command(self._model),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=creationflags())
            tail = []
            for line in self._proc.stdout:
                tail.append(line.rstrip())
                del tail[:-20]
            code = self._proc.wait()
        except OSError as exc:
            self.finished_ok.emit(self._model, False, str(exc))
            return
        if self._cancelled:
            self.finished_ok.emit(self._model, False, "cancelled")
        elif code:
            self.finished_ok.emit(self._model, False,
                                  "\n".join(tail[-3:]) or f"code {code}")
        else:
            self.finished_ok.emit(self._model, True, "")


class GigaamDownloadWorker(QThread):
    finished_ok = Signal(str, bool, str)

    def __init__(self, model_name: str, parent=None):
        super().__init__(parent)
        self._model_name = model_name
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            runtime_env.install_gigaam_model(
                self._model_name, cancelled=lambda: self._cancelled)
        except runtime_env.SetupCancelled:
            self.finished_ok.emit(GIGAAM_KEY, False, "cancelled")
        except Exception as exc:
            self.finished_ok.emit(GIGAAM_KEY, False, str(exc))
        else:
            self.finished_ok.emit(GIGAAM_KEY, True, "")


class DiskUsageWorker(QThread):
    result = Signal(object)  # runtime size in bytes

    def run(self):
        self.result.emit(runtime_env.disk_usage())


class CheckUpdatesWorker(QThread):
    result = Signal(dict)

    def run(self):
        # each check degrades on its own: an exception here would
        # leave the button disabled behind «проверка…» forever
        self.result.emit({
            "app": self._safe(updates.check_app_update,
                              {"current": __version__, "latest": None,
                               "update": False, "url": ""}),
            "packages": self._safe(updates.check_packages, []),
            "models": self._safe(updates.check_whisper_models, []),
        })

    @staticmethod
    def _safe(check, fallback):
        try:
            return check()
        except Exception:
            return fallback


class UpgradeWorker(QThread):
    finished_ok = Signal(bool, str)
    stage = Signal(str, int, int)   # name, index (1-based), total
    progress = Signal(str)          # live line for the group hint

    def __init__(self, package_names, model_names, parent=None):
        super().__init__(parent)
        self._packages = list(package_names)
        self._models = list(model_names)

    def run(self):
        messages = []
        ok = True
        total = len(self._packages) + len(self._models)
        index = 0
        for name in self._packages:
            index += 1
            self.stage.emit(name, index, total)
            pip_ok, tail = updates.pip_upgrade(
                [name], log=lambda line, n=name: self.progress.emit(
                    f"{n}: {line}"))
            ok = ok and pip_ok
            if not pip_ok:
                messages.append(f"{name}: {tail[-300:]}")
        for model in self._models:
            index += 1
            self.stage.emit(model, index, total)
            try:  # snapshot_download fetches the new revision
                models.download_whisper_model(model)
            except Exception as exc:
                ok = False
                messages.append(f"{model}: {exc}")
        self.finished_ok.emit(ok, "\n".join(messages))


# ================================================================ rows
class ModelRow(QFrame):
    """Модель · Состояние (+ progress) · Размер · action."""

    def __init__(self, key: str, name: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setProperty("modelRow", True)
        self.setFixedHeight(44)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(0)
        self.name_label = QLabel(name)
        self.name_label.setObjectName("model_name")
        self.name_label.setFixedWidth(220)
        row.addWidget(self.name_label)

        state_box = QWidget()
        state_box.setObjectName("model_state_box")
        state_box.setFixedWidth(220)
        state_layout = QVBoxLayout(state_box)
        state_layout.setContentsMargins(0, 0, 0, 0)
        state_layout.setSpacing(3)
        state_layout.addStretch()
        self.state_label = QLabel("")
        self.state_label.setObjectName("model_state")
        state_layout.addWidget(self.state_label)
        self.progress = QProgressBar()
        self.progress.setObjectName("model_progress")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)             # HF gives no percent
        self.progress.setFixedSize(130, 3)
        self.progress.setVisible(False)
        state_layout.addWidget(self.progress)
        state_layout.addStretch()
        row.addWidget(state_box)

        self.size_label = QLabel("")
        self.size_label.setObjectName("model_size")
        self.size_label.setFixedWidth(90)
        row.addWidget(self.size_label)
        row.addStretch()

        self.download_button = QPushButton(tr("Download"))
        self.download_button.setObjectName("model_download")
        row.addWidget(self.download_button)
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setObjectName("model_cancel")
        self.cancel_button.setVisible(False)
        row.addWidget(self.cancel_button)
        self.more_button = QToolButton()
        self.more_button.setObjectName("model_more")
        self.more_button.setText("⋯")
        self.more_button.setVisible(False)
        row.addWidget(self.more_button)

    def show_state(self, state: str, text: str, size_text: str):
        """state: none | done | busy | err"""
        self.setProperty("state", state)
        self.state_label.setText(text)
        self.state_label.setProperty("state", state)
        self.size_label.setText(size_text)
        self.size_label.setProperty("state", state)
        self.progress.setVisible(state == "busy")
        self.download_button.setVisible(state in ("none", "err"))
        self.cancel_button.setVisible(state == "busy")
        self.more_button.setVisible(state == "done")
        for widget in (self, self.state_label, self.size_label):
            repolish(widget)


class UpdateRow(QFrame):
    """icon · name · old → new · stretch · state / action."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setProperty("updateRow", True)
        self.setFixedHeight(36)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(10)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("upd_icon")
        row.addWidget(self.icon_label)
        self.name_label = QLabel(name)
        self.name_label.setObjectName("upd_name")
        self.name_label.setFixedWidth(150)
        row.addWidget(self.name_label)
        self.old_label = QLabel("")
        self.old_label.setObjectName("upd_old")
        row.addWidget(self.old_label)
        self.new_label = QLabel("")
        self.new_label.setObjectName("upd_new")
        row.addWidget(self.new_label)
        row.addStretch()
        self.whats_new = QToolButton()
        self.whats_new.setObjectName("upd_whats_new")
        self.whats_new.setText(tr("What's new"))
        self.whats_new.setVisible(False)
        row.addWidget(self.whats_new)
        self.progress = QProgressBar()
        self.progress.setObjectName("upd_progress")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        self.progress.setFixedSize(130, 3)
        self.progress.setVisible(False)
        row.addWidget(self.progress)
        self.state_label = QLabel("")
        self.state_label.setObjectName("upd_state")
        row.addWidget(self.state_label)
        self.button = QPushButton("")
        self.button.setObjectName("upd_row_btn")
        self.button.setVisible(False)
        row.addWidget(self.button)

    def show_state(self, state: str, icon_name: str, old: str = "",
                   new: str = "", status: str = "", button: str = "",
                   accent: bool = False):
        """state: ok | new | err | busy | missing"""
        self.setProperty("state", state)
        self.icon_label.setPixmap(
            ui_icon(icon_name, 12,
                    ACCENT if state == "new" else
                    ERROR_TEXT if state == "err" else MUTED).pixmap(12, 12))
        self.old_label.setText(old)
        self.new_label.setText(f"→ {new}" if new else "")
        self.state_label.setText(status)
        self.state_label.setProperty("state", state)
        self.state_label.setVisible(bool(status))
        self.button.setText(button)
        self.button.setVisible(bool(button))
        self.button.setProperty("accent", accent)
        self.progress.setVisible(state == "busy")
        for widget in (self, self.state_label, self.button):
            repolish(widget)


# ================================================================ the tab
class ModelsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("models_tab")
        self._settings = config.load_settings()
        self._worker = None            # the one running model download
        self._downloading = None
        self._failed = {}              # model key -> last error line
        self._disk_worker = None
        self._runtime_bytes = None     # unknown until the walk finishes
        self._whisper_bytes = 0
        self._gigaam_bytes = 0
        self._updates_worker = None
        self._upgrade_worker = None
        self._outdated_packages = []
        self._outdated_models = []
        self._last_result = None
        self._update_rows = {}

        # three groups are taller than a 760px window once the update
        # list is populated — they scroll inside the tab instead of
        # pushing the main window past a laptop screen
        from PySide6.QtWidgets import QScrollArea
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("models_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 26, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(self._build_device_group())
        layout.addWidget(self._build_models_group())
        layout.addWidget(self._build_service_group())
        layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.refresh()
        self._restore_last_check()

    # ------------------------------------------------------------ device
    def _build_device_group(self) -> QFrame:
        self.group_device = QFrame()
        self.group_device.setObjectName("group_device")
        row = QHBoxLayout(self.group_device)
        row.setContentsMargins(16, 11, 16, 11)
        row.setSpacing(12)
        self.device_icon = QLabel()
        self.device_icon.setObjectName("device_icon")
        row.addWidget(self.device_icon)
        self.device_text = QLabel("")
        self.device_text.setObjectName("device_text")
        row.addWidget(self.device_text)
        self.device_note = ElidedLabel("")
        self.device_note.setObjectName("device_note")
        row.addWidget(self.device_note)
        row.addStretch()
        self.device_settings_link = QToolButton()
        self.device_settings_link.setObjectName("device_settings_link")
        self.device_settings_link.setText(tr("Open settings →"))
        self.device_settings_link.setCursor(Qt.PointingHandCursor)
        self.device_settings_link.clicked.connect(self._goto_settings)
        self.device_settings_link.setVisible(False)
        row.addWidget(self.device_settings_link)

        gpus = gpu.detect_gpus()
        if gpus:
            best = max(gpus, key=lambda x: x.vram_mb)
            # VRAM is quoted in whole gigabytes the way the card is sold
            # («8 ГБ»), not as a byte-exact 7,6
            self.device_text.setText(
                f"{best.name} · {round(best.vram_mb / 1024)} "
                f"{tr('GB')} VRAM")
            self.device_note.setText(
                tr("recognition runs on the graphics card"))
            self.device_icon.setPixmap(
                ui_icon("gpu", 15, ACCENT_TEXT).pixmap(15, 15))
        else:
            self.group_device.setProperty("state", "warn")
            self.device_text.setText(
                tr("No NVIDIA GPU found — recognition runs on the "
                   "processor, 2–4× slower"))
            self.device_note.setText("")
            self.device_icon.setPixmap(
                ui_icon("warning", 16, "#e6d5ae").pixmap(16, 16))
            self.device_settings_link.setVisible(True)
        return self.group_device

    def _goto_settings(self):
        window = self.window()
        if hasattr(window, "tabs") and hasattr(window, "settings_tab"):
            window.tabs.setCurrentWidget(window.settings_tab)
            combo = getattr(window.settings_tab, "device_combo", None)
            if combo is not None:
                combo.setFocus()

    # ------------------------------------------------------------ models
    @staticmethod
    def _group_header(title: str, hint: str):
        head = QHBoxLayout()
        head.setSpacing(8)
        title_label = QLabel(title)
        title_label.setProperty("groupTitle", True)
        head.addWidget(title_label)
        hint_label = ElidedLabel(hint)
        hint_label.setProperty("groupHint", True)
        head.addWidget(hint_label)
        head.addStretch()
        return head, hint_label

    def _build_models_group(self) -> QFrame:
        self.group_models = QFrame()
        self.group_models.setObjectName("group_models")
        box = QVBoxLayout(self.group_models)
        box.setContentsMargins(16, 14, 16, 12)
        box.setSpacing(0)
        head, _ = self._group_header(
            tr("Recognition models"),
            tr("what is downloaded and how much disk it takes"))
        box.addLayout(head)
        box.addSpacing(10)

        columns = QHBoxLayout()
        # the sheet pads the head labels 10px, matching the rows' margin
        columns.setContentsMargins(0, 0, 0, 4)
        columns.setSpacing(0)
        for text, width, align in ((tr("Model"), 220, Qt.AlignLeft),
                                   (tr("State"), 220, Qt.AlignLeft),
                                   (tr("Size"), 90, Qt.AlignRight)):
            label = QLabel(text)
            label.setProperty("tableHead", True)
            label.setFixedWidth(width)
            label.setAlignment(align | Qt.AlignVCenter)
            columns.addWidget(label)
        columns.addStretch()
        box.addLayout(columns)

        self.model_rows = {}
        box.addWidget(self._caption("WHISPER"))
        for model in WHISPER_MODELS:
            box.addWidget(self._make_model_row(model, model))
        box.addWidget(self._caption(tr("GIGAAM · RUSSIAN ENGINE")))
        gigaam_name = "GigaAM " + self._settings.get(
            "gigaam_model", "v3_rnnt").split("_")[0]
        box.addWidget(self._make_model_row(GIGAAM_KEY, gigaam_name))

        # disk usage: caption + legend, then the stacked bar
        self.disk_summary = QWidget()
        self.disk_summary.setObjectName("disk_summary")
        disk_box = QVBoxLayout(self.disk_summary)
        disk_box.setContentsMargins(10, 12, 10, 2)
        disk_box.setSpacing(8)
        legend = QHBoxLayout()
        legend.setSpacing(14)
        self.disk_total = QLabel("")
        self.disk_total.setObjectName("disk_total")
        legend.addWidget(self.disk_total)
        legend.addStretch()
        self.disk_legend = {}
        for key in ("components", "whisper", "gigaam"):
            item = QHBoxLayout()
            item.setSpacing(5)
            dot = QFrame()
            dot.setProperty("diskDot", key)
            item.addWidget(dot)
            label = QLabel("")
            label.setProperty("diskLegend", True)
            item.addWidget(label)
            legend.addLayout(item)
            self.disk_legend[key] = label
        disk_box.addLayout(legend)
        bar_frame = QFrame()
        bar_frame.setFixedHeight(8)
        bar = QHBoxLayout(bar_frame)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(2)
        self.disk_segments = {}
        for key in ("components", "whisper", "gigaam"):
            segment = QFrame()
            segment.setProperty("diskSeg", key)
            segment.setFixedHeight(8)
            bar.addWidget(segment)
            self.disk_segments[key] = segment
        self._disk_bar = bar
        disk_box.addWidget(bar_frame)
        box.addWidget(self.disk_summary)
        return self.group_models

    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("tableCap", True)
        return label

    def _make_model_row(self, key: str, name: str) -> ModelRow:
        row = ModelRow(key, name)
        row.download_button.clicked.connect(
            lambda _=False, k=key: self._download(k))
        row.cancel_button.clicked.connect(self._cancel_download)
        row.more_button.clicked.connect(
            lambda _=False, k=key: self._row_menu(k))
        self.model_rows[key] = row
        return row

    def showEvent(self, event):
        super().showEvent(event)
        # the runtime walk is deferred until the tab is actually opened
        if self._runtime_bytes is None:
            self._refresh_disk()

    def refresh(self):
        """Re-read what is on disk and repaint every model row."""
        status = {st["model"]: st for st in models.whisper_model_status()}
        busy = self._worker is not None
        for model in WHISPER_MODELS:
            st = status.get(model, {"downloaded": False, "size_bytes": 0})
            self._paint_row(model, st["downloaded"],
                            st["size_bytes"] or 0, busy)
        caches = models.gigaam_cache_dirs()
        gigaam_bytes = sum(size for _, size in caches)
        self._paint_row(GIGAAM_KEY, bool(caches), gigaam_bytes, busy)
        self._whisper_bytes = sum((st["size_bytes"] or 0)
                                  for st in status.values()
                                  if st["downloaded"])
        self._gigaam_bytes = gigaam_bytes
        self._update_disk_summary()

    def _paint_row(self, key: str, downloaded: bool, size: int,
                   busy: bool):
        row = self.model_rows[key]
        catalogue = models.MODEL_CATALOG_BYTES.get(key, 0)
        if key == self._downloading:
            row.show_state("busy", tr("downloading…"),
                           fmt_bytes(catalogue))
        elif key in self._failed:
            row.show_state("err", tr("failed — {}").format(self._failed[key]),
                           fmt_bytes(catalogue))
            row.download_button.setText(tr("Retry"))
        elif downloaded:
            row.show_state("done", tr("downloaded ✓"), fmt_bytes(size))
        else:
            row.show_state("none", tr("not downloaded"),
                           fmt_bytes(catalogue))
            row.download_button.setText(tr("Download"))
        # during any download every other action is disabled
        for button in (row.download_button, row.more_button):
            button.setEnabled(not busy or key == self._downloading)

    # ------------------------------------------------- model actions
    def _download(self, key: str):
        if self._worker is not None:
            return
        self._failed.pop(key, None)
        self._downloading = key
        if key == GIGAAM_KEY:
            self._worker = GigaamDownloadWorker(
                self._settings.get("gigaam_model", "v3_rnnt"))
        else:
            self._worker = WhisperDownloadWorker(key)
        self._worker.finished_ok.connect(self._on_download_finished)
        start_thread(self, self._worker)
        self.refresh()

    def _cancel_download(self):
        if self._worker is not None:
            self._worker.cancel()

    def _on_download_finished(self, key: str, ok: bool, message: str):
        self._worker = None
        self._downloading = None
        if ok:
            window = self.window()
            if window is not None and hasattr(window, "tabs"):
                from .toasts import show_toast
                show_toast(window, tr("Model downloaded"),
                           self.model_rows[key].name_label.text())
        elif message != "cancelled":
            self._failed[key] = message.splitlines()[-1][:80]
        self.refresh()

    def _row_menu(self, key: str):
        row = self.model_rows[key]
        menu = themed_menu(self, "model_row_menu")
        act_open = menu.addAction(tr("Open folder"))
        menu.addSeparator()
        act_delete = menu.addAction(tr("Delete…"))
        mark_danger(act_delete)
        chosen = menu.exec(row.more_button.mapToGlobal(
            row.more_button.rect().bottomLeft()))
        if chosen is act_open:
            self._open_folder(key)
        elif chosen is act_delete:
            self._delete(key)

    def _open_folder(self, key: str):
        if key == GIGAAM_KEY:
            caches = models.gigaam_cache_dirs()
            target = caches[0][0] if caches else models.hf_hub_cache()
        else:
            target = models.repo_cache_dir(models.WHISPER_REPOS[key])
            if not target.is_dir():
                target = models.hf_hub_cache()
        subprocess.Popen(["explorer", str(target)])

    def _delete(self, key: str):
        name = self.model_rows[key].name_label.text()
        if key == GIGAAM_KEY:
            if confirm(self, title=tr("Delete the GigaAM model caches?"),
                       body=tr("They are downloaded again on the next "
                               "GigaAM pass."),
                       ok_text=tr("Delete caches")):
                models.delete_gigaam_caches()
                self.refresh()
            return
        if confirm(self,
                   title=tr("Delete the downloaded '{}' model?").format(name),
                   body=tr("It is downloaded again the next time it is "
                           "used."),
                   ok_text=tr("Delete model")):
            models.delete_whisper_model(key)
            self.refresh()

    # ---------------------------------------------------------- disk bar
    def _update_disk_summary(self):
        sizes = {"components": self._runtime_bytes,
                 "whisper": self._whisper_bytes,
                 "gigaam": self._gigaam_bytes}
        known = sum(v for v in sizes.values() if v)
        self.disk_total.setText(
            tr("Disk usage · {}").format(fmt_bytes(known)))
        names = {"components": tr("components"), "whisper": "Whisper",
                 "gigaam": "GigaAM"}
        for key, label in self.disk_legend.items():
            size = sizes[key]
            label.setText(f"{names[key]} "
                          + (fmt_bytes(size) if size is not None else "…"))
        for key, segment in self.disk_segments.items():
            size = sizes[key] or 0
            segment.setVisible(size > 0)
            # Qt stretch factors are 32-bit ints: scale to MB
            self._disk_bar.setStretchFactor(
                segment, max(int(size / 1_000_000), 1) if size else 0)

    def _refresh_disk(self):
        if self._disk_worker is not None:
            return
        self._disk_worker = DiskUsageWorker()
        self._disk_worker.result.connect(self._on_disk_result)
        start_thread(self, self._disk_worker)

    def _on_disk_result(self, size):
        self._disk_worker = None
        self._runtime_bytes = size
        self._update_disk_summary()

    # ----------------------------------------------------------- service
    def _build_service_group(self) -> QFrame:
        self.group_service = QFrame()
        self.group_service.setObjectName("group_service")
        box = QVBoxLayout(self.group_service)
        box.setContentsMargins(16, 14, 16, 12)
        box.setSpacing(8)
        head, self.service_hint = self._group_header(
            tr("Maintenance"), tr("updates and repair of the install"))
        self.upd_checked_at = ElidedLabel("")
        self.upd_checked_at.setObjectName("upd_checked_at")
        head.insertWidget(2, self.upd_checked_at)
        self.btn_check = QPushButton("")
        self.btn_check.setObjectName("btn_check")
        self.btn_check.clicked.connect(self._check_button_clicked)
        head.addWidget(self.btn_check)
        box.addLayout(head)
        self.set_check_mode("check")

        self._rows_box = QVBoxLayout()
        self._rows_box.setSpacing(6)
        box.addLayout(self._rows_box)
        self.upd_placeholder = QLabel(
            tr("Press «Check for updates» to see whether newer versions "
               "of the engines and models exist."))
        self.upd_placeholder.setObjectName("upd_footnote")
        self.upd_placeholder.setWordWrap(True)
        box.addWidget(self.upd_placeholder)
        self.upd_footnote = QLabel(
            tr("GigaAM weights update together with the onnx-asr "
               "package."))
        self.upd_footnote.setObjectName("upd_footnote")
        self.upd_footnote.setVisible(False)
        box.addWidget(self.upd_footnote)

        footer = QWidget()
        footer.setObjectName("svc_footer")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(0, 10, 0, 0)
        foot.setSpacing(10)
        self.btn_component_install = QPushButton(
            tr("Add components…"))
        self.btn_component_install.setObjectName("btn_component_install")
        self.btn_component_install.clicked.connect(self._open_components)
        foot.addWidget(self.btn_component_install)
        svc_hint = ElidedLabel(
            tr("the wizard adds what is missing and leaves the rest "
               "alone"))
        svc_hint.setObjectName("svc_hint")
        foot.addWidget(svc_hint)
        foot.addStretch()
        self.btn_repair_link = QToolButton()
        self.btn_repair_link.setObjectName("btn_repair_link")
        self.btn_repair_link.setText(tr("Repair components…"))
        self.btn_repair_link.setCursor(Qt.PointingHandCursor)
        self.btn_repair_link.clicked.connect(self._repair_components)
        foot.addWidget(self.btn_repair_link)
        repair_hint = ElidedLabel(tr("clean start of the runtime"))
        repair_hint.setObjectName("svc_repair_hint")
        foot.addWidget(repair_hint)
        box.addWidget(footer)
        return self.group_service

    def set_check_mode(self, mode: str, count: int = 0):
        """One button that morphs instead of a row that jumps."""
        self.btn_check.setProperty("mode", mode)
        self.btn_check.setText(
            tr("Check for updates") if mode == "check"
            else tr("Update all ({})").format(count))
        repolish(self.btn_check)

    def _check_button_clicked(self):
        if self.btn_check.property("mode") == "update":
            self._update_all()
        else:
            self._check_updates()

    # ------------------------------------------------- update rows
    def _clear_rows(self):
        while self._rows_box.count():
            item = self._rows_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._update_rows = {}

    def _add_row(self, key: str, name: str) -> UpdateRow:
        row = UpdateRow(name)
        self._rows_box.addWidget(row)
        self._update_rows[key] = row
        return row

    def _restore_last_check(self):
        """The tab shows the last known result, not emptiness."""
        last = self._settings.get("updates_last")
        if isinstance(last, dict) and "result" in last:
            self._render_result(last["result"], last.get("at", ""))

    def _check_updates(self):
        if self._updates_worker is not None:
            return
        self.btn_check.setEnabled(False)
        self.service_hint.setText(tr("checking for updates…"))
        self._updates_worker = CheckUpdatesWorker()
        self._updates_worker.result.connect(self._on_updates_result)
        start_thread(self, self._updates_worker)

    def _on_updates_result(self, result: dict):
        self._updates_worker = None
        self.btn_check.setEnabled(True)
        stamp = datetime.now().isoformat(timespec="seconds")
        self._settings["updates_last"] = {"at": stamp, "result": result}
        try:
            config.save_settings(self._settings)
        except OSError:
            pass
        self._render_result(result, stamp)

    def _render_result(self, result: dict, checked_at: str):
        self._last_result = result
        self._clear_rows()
        self._outdated_packages = []
        self._outdated_models = []
        self.upd_placeholder.setVisible(False)
        self.upd_footnote.setVisible(True)
        self.service_hint.setText(tr("updates and repair of the install"))
        self.upd_checked_at.setText(
            "· " + tr("checked {}").format(human_datetime(checked_at))
            if checked_at else "")

        app = result.get("app")
        if app:
            row = self._add_row("app", "WordMute")
            if app.get("update"):
                row.show_state("new", "arrow-up", app["current"],
                               app["latest"], button=tr("Download"),
                               accent=True)
                row.whats_new.setVisible(True)
                row.whats_new.clicked.connect(
                    lambda _=False, u=app["url"]: self._open_url(u))
                row.button.clicked.connect(
                    lambda _=False, u=app["url"]: self._open_url(u))
            elif app.get("latest") is None:
                row.show_state("err", "warning", app["current"],
                               status=tr("could not check"),
                               button=tr("Retry"))
                row.button.clicked.connect(self._check_updates)
            else:
                row.show_state("ok", "check", app["current"],
                               status=tr("up to date"))
        for pkg in result.get("packages", []):
            row = self._add_row(pkg["name"], pkg["name"])
            if pkg["installed"] is None:
                row.show_state("missing", "warning",
                               status=tr("not installed"),
                               button=tr("Install"))
                row.button.clicked.connect(self._open_components)
            elif pkg["latest"] is None:
                row.show_state("err", "warning", pkg["installed"],
                               status=tr("could not check"),
                               button=tr("Retry"))
                row.button.clicked.connect(self._check_updates)
            elif pkg["update"]:
                self._outdated_packages.append(pkg["name"])
                row.show_state("new", "arrow-up", pkg["installed"],
                               pkg["latest"], button=tr("Update"))
                row.button.clicked.connect(
                    lambda _=False, n=pkg["name"]: self._update_all([n], []))
            else:
                row.show_state("ok", "check", pkg["installed"],
                               status=tr("up to date"))
        for model in result.get("models", []):
            row = self._add_row("model:" + model["model"],
                                tr("{} model").format(model["model"]))
            if model["update"]:
                self._outdated_models.append(model["model"])
                row.show_state("new", "arrow-up", tr("current revision"),
                               tr("new revision"), button=tr("Update"))
                row.button.clicked.connect(
                    lambda _=False, m=model["model"]:
                    self._update_all([], [m]))
            else:
                row.show_state("ok", "check", tr("current revision"),
                               status=tr("up to date"))
        count = len(self._outdated_packages) + len(self._outdated_models)
        self.set_check_mode("update" if count else "check", count)

    @staticmethod
    def _open_url(url: str):
        import webbrowser
        webbrowser.open(url)

    # ------------------------------------------------- updating
    def _update_all(self, packages=None, model_names=None):
        if self._upgrade_worker is not None:
            return
        packages = (list(self._outdated_packages) if packages is None
                    else packages)
        model_names = (list(self._outdated_models) if model_names is None
                       else model_names)
        if not packages and not model_names:
            return
        self.btn_check.setEnabled(False)
        self._upgrade_worker = UpgradeWorker(packages, model_names)
        self._upgrade_worker.stage.connect(self._on_upgrade_stage)
        self._upgrade_worker.progress.connect(self._on_upgrade_progress)
        self._upgrade_worker.finished_ok.connect(self._on_upgrade_done)
        start_thread(self, self._upgrade_worker)

    def _on_upgrade_stage(self, name: str, index: int, total: int):
        self.service_hint.setText(
            tr("updating {} of {}").format(index, total))
        row = self._update_rows.get(name) or self._update_rows.get(
            "model:" + name)
        if row is not None:
            row.show_state("busy", "arrow-up", row.old_label.text(),
                           row.new_label.text().lstrip("→ "))

    def _on_upgrade_progress(self, line: str):
        # one live line: pip's download lines carry the version and
        # the size — the reassurance a frozen label was missing
        if len(line) > 90:
            line = line[:50] + "…" + line[-35:]
        self.service_hint.setText(line)

    def _on_upgrade_done(self, ok: bool, message: str):
        self._upgrade_worker = None
        self.btn_check.setEnabled(True)
        if ok:
            window = self.window()
            if window is not None and hasattr(window, "tabs"):
                from .toasts import show_toast
                show_toast(window, tr("Updates installed"),
                           tr("Restart the app to use them."))
            # re-check: the rows turn green on their own
            self._check_updates()
        else:
            self.service_hint.setText(
                tr("Update failed: {}").format(message[:120]))
            inform(self, title=tr("Update failed"), body=message)
            if self._last_result:
                self._render_result(self._last_result, "")
        self.refresh()

    # ----------------------------------------------- wizard / repair
    def _open_components(self):
        from .setup_dialog import SetupDialog
        SetupDialog(self, first_run=False).exec()
        self.refresh()
        self._refresh_disk()

    def _repair_components(self):
        """The standard clean retry from INSTALL_GUIDE, as one click:
        delete the managed runtime, then run the component setup."""
        if not confirm(self,
                       title=tr("Delete the runtime and set it up again?"),
                       body=tr("Word lists, settings, history and the "
                               "downloaded models are kept. Best done "
                               "right after starting the app, before any "
                               "processing."),
                       ok_text=tr("Delete and set up")):
            return
        import shutil
        shutil.rmtree(runtime_env.runtime_dir(), ignore_errors=True)
        self._open_components()
        inform(self, title=tr("Restart the app to use the reinstalled "
                              "components."))

    def shutdown(self):
        for worker in (self._worker, self._updates_worker,
                       self._upgrade_worker, self._disk_worker):
            wait_thread(worker, 30000)
