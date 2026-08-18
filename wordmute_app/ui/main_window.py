"""Main window: file/folder queue with per-file progress, word list
selection, pass plan builder, settings dialog, run with live status."""

import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core import config, gpu, thumbs
from ..core.jobs import (JobOptions, QueueItem, build_plan, expand_inputs,
                         scan_watch_dir)
from ..core.probe import media_duration
from ..core.wordlists import merge_wordlists
from .dialogs import confirm, inform, mark_danger, themed_menu
from .events import format_event
from .formats import fmt_rate
from .history_tab import HistoryTab
from .i18n import tr
from .models_tab import ModelsTab
from .plan_widget import PassPlanWidget
from .queue_card import QueueCard
from .review_dialog import ReviewDialog
from .settings_tab import SettingsTab
from .sidebar import SidebarNav
from .transcript_tab import TranscriptTab
from .url_dialog import AddUrlDialog
from .wordlists_tab import WordListsTab
from .worker import ProcessWorker

# data roles on each queue QListWidgetItem. Cards are rebuilt from
# these after drag-reorders (Qt destroys item widgets on internal
# moves), so everything a card shows must live here.
ITEM_ROLE = Qt.UserRole            # the QueueItem object
REVIEW_ROLE = Qt.UserRole + 1      # path of the review sidecar
OUTPUT_ROLE = Qt.UserRole + 2      # path of the produced output file
DURATION_ROLE = Qt.UserRole + 3    # media duration in seconds
STATUS_ROLE = Qt.UserRole + 4      # current status text
STATE_ROLE = Qt.UserRole + 5       # status color state (ok/err/None)
THUMB_ROLE = Qt.UserRole + 6       # cached thumbnail path ("" = none)
TITLE_ROLE = Qt.UserRole + 7       # card title (changes after download)
META_ROLE = Qt.UserRole + 8        # card meta line


def fmt_duration(sec) -> str:
    if sec is None:
        return "—"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_hms(sec: float) -> str:
    """Humanized duration: '45 s', '1 min 29 s', '1 h 5 min'."""
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    _h, _m, _s = tr("h"), tr("min"), tr("s")
    if h:
        return f"{h} {_h} {m} {_m}" if m else f"{h} {_h}"
    if m:
        return f"{m} {_m} {s} {_s}" if s else f"{m} {_m}"
    return f"{s} {_s}"


def fmt_eta(sec: float) -> str:
    return tr("~{} left").format(fmt_hms(max(sec, 1)))


def _initial_size(avail_w: int, avail_h: int) -> tuple:
    """Preferred 960x720, shrunk to fit the available desktop (with a
    small margin for window chrome); 0/negative = unknown screen."""
    width, height = 960, 720
    if avail_w > 0:
        width = max(480, min(width, avail_w - 24))
    if avail_h > 0:
        height = max(360, min(height, avail_h - 48))
    return width, height


def fmt_speed(bps) -> str:
    """Kept as a thin alias: the queue cards and the download pump both
    call it, the units and decimal comma now come from the locale."""
    return fmt_rate(bps)


class AppUpdateWorker(QThread):
    result = Signal(dict)

    def run(self):
        from ..core import updates
        self.result.emit(updates.check_app_update())


class MediaProbeWorker(QThread):
    """Bulk adds defer the per-file ffprobe (duration) and ffmpeg
    thumbnail grab here, so queueing a folder never freezes the UI;
    results stream back one card at a time."""
    ready = Signal(object, object, str)  # QueueItem, duration, thumb

    def __init__(self, parent=None):
        super().__init__(parent)
        from queue import SimpleQueue
        self._jobs = SimpleQueue()

    def enqueue(self, item):
        self._jobs.put(item)

    def stop(self):
        self._jobs.put(None)

    def run(self):
        while True:
            item = self._jobs.get()
            if item is None:
                return
            duration = media_duration(item.path)
            thumb = thumbs.thumbnail_path(item.path)
            self.ready.emit(item, duration, str(thumb) if thumb else "")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WordMute")
        # clamp the preferred size to the available screen: small
        # laptops (and Windows text-only scaling) must not get a window
        # larger than the desktop
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        self.resize(*_initial_size(avail.width() if avail else 0,
                                   avail.height() if avail else 0))
        self.setAcceptDrops(True)

        self._worker = None
        self._active_rows = []  # queue rows of the current run, in order
        self._review_windows = []
        # tray icon: click raises the window; used for the
        # queue-finished notification when the app is in the background
        from PySide6.QtWidgets import QSystemTrayIcon
        self._tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(self.windowIcon(), self)
            self._tray.setToolTip("WordMute")
            self._tray.activated.connect(self._on_tray_activated)
            self._tray.show()
        # quiet self-update check, a few seconds after startup
        self._app_update_worker = None
        self._update_url = None
        QTimer.singleShot(3000, self._start_update_check)
        self._probe_worker = None  # lazy: bulk-add duration/thumb jobs
        self._wordlist_paths = config.ensure_user_wordlists()
        self._settings = config.load_settings()
        self._gpus = gpu.detect_gpus()
        self._reset_run_state(total=0)
        self._watch_dir = None
        self._watch_seen = {}
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(5000)
        self._watch_timer.timeout.connect(self._watch_tick)

        # --- shell: header strip + sidebar navigation (no menu bar)
        from .theme import app_icon
        container = QWidget()
        shell = QVBoxLayout(container)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        header_bar = QWidget()
        header_bar.setObjectName("header_bar")
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(16, 8, 16, 8)
        header_layout.setSpacing(8)
        icon_label = QLabel()
        icon_label.setPixmap(app_icon().pixmap(20, 20))
        header_layout.addWidget(icon_label)
        title_label = QLabel("WordMute")
        title_label.setObjectName("app_title")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        shell.addWidget(header_bar)
        self.tabs = SidebarNav()
        shell.addWidget(self.tabs, stretch=1)
        self.setCentralWidget(container)

        queue_page = QWidget()
        page_layout = QVBoxLayout(queue_page)
        page_layout.setContentsMargins(20, 16, 20, 16)
        page_layout.setSpacing(0)
        upper = QWidget()
        root = QVBoxLayout(upper)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # --- file queue
        file_buttons = QHBoxLayout()
        self.add_button = QPushButton(tr("Add Files"))
        self.add_button.clicked.connect(self._pick_files)
        self.add_folder_button = QPushButton(tr("Add Folder"))
        self.add_folder_button.clicked.connect(self._pick_folder)
        # lambda: clicked(checked) must not leak its bool into url=
        self.add_url_button = QPushButton(tr("Add URL"))
        self.add_url_button.clicked.connect(lambda: self._add_url())
        self.remove_button = QPushButton(tr("Remove Selected"))
        self.remove_button.clicked.connect(self._remove_selected)
        self.remove_button.setProperty("danger", True)
        file_buttons.setSpacing(8)
        file_buttons.addWidget(self.add_button)
        file_buttons.addWidget(self.add_folder_button)
        file_buttons.addWidget(self.add_url_button)
        file_buttons.addSpacing(16)
        file_buttons.addWidget(self.remove_button)
        # everything less-used lives in one ⋯ menu (design v3)
        from PySide6.QtWidgets import QMenu
        self.more_button = QToolButton()
        self.more_button.setText("⋯ " + tr("More"))
        self.more_button.setPopupMode(QToolButton.InstantPopup)
        more_menu = QMenu(self.more_button)
        # (the GigaAM/Hugging-Face wizard is gone: setup installs GigaAM
        #  via onnx-asr, which needs no account)
        self.watch_action = more_menu.addAction(tr("Watch Folder"),
                                                self._toggle_watch)
        more_menu.addSeparator()
        more_menu.addAction(tr("Open review file…"), self._pick_review)
        self.more_button.setMenu(more_menu)
        file_buttons.addStretch()
        file_buttons.addWidget(self.more_button)
        root.addLayout(file_buttons)

        # queue as cards (design v3)
        from .queue_card import QueueList
        self.queue = QueueList()
        self.queue.setObjectName("queue_cards")
        self.queue.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # pick-up-and-drop reorder (no native QDrag: it would destroy
        # the card widgets mid-move and can't animate the others aside)
        from .animated_reorder import AnimatedReorder
        self._queue_reorder = AnimatedReorder(
            self.queue, self._move_queue_row,
            lift_radius=8)  # QFrame[videoCard] border-radius
        self.queue.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.queue.itemSelectionChanged.connect(self._mirror_selection)
        self.queue.setContextMenuPolicy(Qt.CustomContextMenu)
        self.queue.customContextMenuRequested.connect(
            lambda pos: self._card_menu(
                self.queue.row(self.queue.itemAt(pos)),
                self.queue.viewport().mapToGlobal(pos)))

        # empty state shown until the first item is queued
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch()
        empty_title = QLabel(tr("Drop video or audio files here"))
        empty_title.setObjectName("empty_state_title")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_body = QLabel(tr(
            "…or paste a link with Add URL. Matched words from your word "
            "lists are muted; the video stays untouched.\n"
            "Everything runs on this computer — nothing is uploaded."))
        empty_body.setObjectName("empty_state_body")
        empty_body.setAlignment(Qt.AlignCenter)
        empty_body.setWordWrap(True)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_body)
        empty_buttons = QHBoxLayout()
        empty_buttons.addStretch()
        empty_add = QPushButton(tr("Add Files"))
        empty_add.setProperty("primary", True)
        empty_add.clicked.connect(self._pick_files)
        empty_view_lists = QPushButton(tr("View word lists"))
        empty_view_lists.clicked.connect(
            lambda: self.tabs.setCurrentWidget(self.wordlists_tab))
        empty_buttons.addWidget(empty_add)
        empty_buttons.addWidget(empty_view_lists)
        empty_buttons.addStretch()
        empty_layout.addSpacing(12)
        empty_layout.addLayout(empty_buttons)
        empty_layout.addStretch()

        self.queue_stack = QStackedWidget()
        self.queue_stack.addWidget(empty)
        self.queue_stack.addWidget(self.queue)
        root.addWidget(self.queue_stack, stretch=2)

        # --- setup: collapsed summary bar, expandable panel
        self.setup_bar = QWidget()
        self.setup_bar.setObjectName("setup_bar")
        setup_bar_layout = QHBoxLayout(self.setup_bar)
        setup_bar_layout.setContentsMargins(12, 6, 12, 6)
        self.setup_summary = QLabel("")
        self.setup_summary.setObjectName("setup_summary")
        # never force window width; long plans clip with a tooltip
        from PySide6.QtWidgets import QSizePolicy
        self.setup_summary.setSizePolicy(QSizePolicy.Ignored,
                                         QSizePolicy.Preferred)
        setup_bar_layout.addWidget(self.setup_summary, stretch=1)
        self.setup_toggle = QPushButton(tr("Change…"))
        self.setup_toggle.clicked.connect(self._toggle_setup_panel)
        setup_bar_layout.addWidget(self.setup_toggle)
        root.addWidget(self.setup_bar)

        self.setup_panel = QWidget()
        options_row = QHBoxLayout(self.setup_panel)
        options_row.setContentsMargins(0, 0, 0, 0)
        options_row.setSpacing(20)
        lists_box = QGroupBox(tr("Word lists"))
        lists_layout = QVBoxLayout(lists_box)
        self.russian_check = QCheckBox(tr("Russian list"))
        self.russian_check.setChecked(self._settings["use_russian"])
        self.english_check = QCheckBox(tr("English list"))
        self.english_check.setChecked(self._settings["use_english"])
        lists_layout.addWidget(self.russian_check)
        lists_layout.addWidget(self.english_check)
        self.force_passes_check = QCheckBox(tr("Force all passes"))
        self.force_passes_check.setChecked(self._settings["force_passes"])
        self.force_passes_check.setToolTip(
            tr("Run every pass even if an earlier one finds nothing; the "
               "final pass re-transcribes completely fresh, ignoring "
               "caches."))
        self.retranscribe_check = QCheckBox(tr("Ignore cached transcripts"))
        self.retranscribe_check.setToolTip(
            tr("Re-transcribe from scratch on the first pass (one-off; "
               "not remembered)."))
        lists_layout.addWidget(self.force_passes_check)
        lists_layout.addWidget(self.retranscribe_check)
        lists_layout.addStretch()
        options_row.addWidget(lists_box, stretch=1)

        self.plan = PassPlanWidget()
        self.plan.set_engines(self._settings["plan"])
        self.plan.changed.connect(self._refresh_warnings)
        self.plan.changed.connect(self._update_setup_summary)
        options_row.addWidget(self.plan, stretch=2)
        self.setup_panel.setVisible(False)
        root.addWidget(self.setup_panel)
        for check in (self.russian_check, self.english_check):
            check.toggled.connect(self._update_setup_summary)
            check.toggled.connect(self._refresh_warnings)
        self._update_setup_summary()

        self.warnings_label = QLabel("")
        self.warnings_label.setObjectName("warnings_label")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setVisible(False)
        root.addWidget(self.warnings_label)
        self._refresh_warnings()

        # --- run controls + live status
        run_row = QHBoxLayout()
        run_row.setSpacing(8)
        self.start_button = QPushButton(tr("Start"))
        self.start_button.setProperty("primary", True)
        self.start_button.clicked.connect(lambda: self._start())
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setEnabled(False)
        run_row.addWidget(self.start_button)
        run_row.addWidget(self.cancel_button)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        run_row.addWidget(self.progress_bar, stretch=1)
        self.percent_label = QLabel("")
        self.percent_label.setProperty("muted", True)
        run_row.addWidget(self.percent_label)
        root.addLayout(run_row)

        self.status_label = QLabel(tr("Ready."))
        self.status_label.setObjectName("status_label")
        root.addWidget(self.status_label)

        self.log_toggle = QToolButton()
        self.log_toggle.setText(tr("Details"))
        self.log_toggle.setCheckable(True)
        self.log_toggle.setArrowType(Qt.RightArrow)
        self.log_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.log_toggle.toggled.connect(self._toggle_log)
        root.addWidget(self.log_toggle)

        # log lives in a splitter so the Details pane is resizable
        self.log = QPlainTextEdit()
        self.log.setObjectName("log_pane")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setVisible(False)
        from PySide6.QtWidgets import QSplitter
        self.queue_splitter = QSplitter(Qt.Vertical)
        self.queue_splitter.addWidget(upper)
        self.queue_splitter.addWidget(self.log)
        self.queue_splitter.setStretchFactor(0, 4)
        self.queue_splitter.setStretchFactor(1, 1)
        self.queue_splitter.setCollapsible(0, False)
        page_layout.addWidget(self.queue_splitter)
        queue_tab = queue_page

        # --- assemble navigation
        from .theme import nav_icon
        self.tabs.addTab(queue_tab, tr("Queue"), nav_icon("queue"))
        self.wordlists_tab = WordListsTab(self._wordlist_paths,
                                          self._settings)
        self.wordlists_tab.dirtyChanged.connect(
            lambda dirty: self.tabs.setTabText(
                1, tr("Word Lists") + (" •" if dirty else "")))
        self.tabs.addTab(self.wordlists_tab, tr("Word Lists"),
                         nav_icon("wordlists"))
        self.transcript_tab = TranscriptTab()
        self.tabs.addTab(self.transcript_tab, tr("Transcript"),
                         nav_icon("transcript"))
        self.models_tab = ModelsTab()
        self.tabs.addTab(self.models_tab, tr("Models"), nav_icon("models"))
        self.history_tab = HistoryTab()
        self.tabs.addTab(self.history_tab, tr("History"),
                         nav_icon("history"))
        self.settings_tab = SettingsTab(self._settings)
        self.settings_tab.changed.connect(self._refresh_warnings)
        self.tabs.addTab(self.settings_tab, tr("Settings"),
                         nav_icon("settings"))
        self.tabs.currentChanged.connect(self._on_tab_changed)

    # ---------------------------------------------------------- queue chrome
    def _toggle_setup_panel(self):
        show = not self.setup_panel.isVisible()
        self.setup_panel.setVisible(show)
        self.setup_toggle.setText(tr("Hide") if show else tr("Change…"))

    def _update_setup_summary(self):
        from itertools import groupby
        lists = []
        if self.russian_check.isChecked():
            lists.append(tr("Russian"))
        if self.english_check.isChecked():
            lists.append(tr("English"))
        engines = self.plan.engines()
        # compact: consecutive repeats collapse to "GigaAM ×2"
        parts = []
        for engine, run in groupby(engines):
            count = len(list(run))
            name = "GigaAM" if engine == "gigaam" else "Whisper"
            parts.append(name if count == 1 else f"{name} ×{count}")
        plan_text = " → ".join(parts) or tr("empty")
        text = (f"{tr('Word lists')}: {', '.join(lists) or tr('none')} · "
                f"{tr('Pass plan')}: {plan_text}")
        self.setup_summary.setText(text)
        self.setup_summary.setToolTip(text)

    def _toggle_log(self, checked: bool):
        self.log.setVisible(checked)
        self.log_toggle.setArrowType(
            Qt.DownArrow if checked else Qt.RightArrow)

    def _update_queue_stack(self):
        self.queue_stack.setCurrentWidget(
            self.queue if self.queue.count() else
            self.queue_stack.widget(0))

    def _on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)
        # data shown in these tabs can change while other tabs work
        if widget is self.history_tab:
            self.history_tab.refresh()
        elif widget is self.models_tab:
            self.models_tab.refresh()

    # ---------------------------------------------------------- watch folder
    def _toggle_watch(self):
        if self._watch_dir is not None:
            self._watch_timer.stop()
            self._watch_dir = None
            self._watch_seen = {}
            self.watch_action.setText(tr("Watch Folder"))
            self.status_label.setText(tr("Ready."))
            return
        d = QFileDialog.getExistingDirectory(
            self, "Watch folder", self._settings.get("watch_dir", ""))
        if not d:
            return
        self._watch_dir = Path(d)
        self._settings["watch_dir"] = d
        config.save_settings(self._settings)
        # files already present are treated as known, not auto-queued
        self._watch_seen = {}
        scan_watch_dir(self._watch_dir, self._watch_seen)
        for state in self._watch_seen.values():
            state[1] = True
        self._watch_timer.start()
        self.watch_action.setText(tr("Stop Watching"))
        self.status_label.setText(
            tr("Watching {} — new media files are queued and processed "
               "automatically.").format(d))
        self._append_log(f"Watching folder: {d}")

    def _watch_tick(self):
        if self._watch_dir is None:
            return
        new_files = scan_watch_dir(self._watch_dir, self._watch_seen)
        if new_files:
            self._add_files(new_files)
            self._append_log("Watch folder: queued "
                             + ", ".join(f.name for f in new_files))
        if self._worker is None and self._queued_rows():
            self._start(auto=True)

    def _queued_rows(self) -> list:
        return [r for r in range(self.queue.count())
                if self.status_text(r).startswith(tr("queued"))]

    def _clear_finished_rows(self):
        for row in reversed(range(self.queue.count())):
            if not self.status_text(row).startswith(tr("queued")):
                self.queue.takeItem(row)
        self._update_queue_stack()

    # ---------------------------------------------------------- queue
    def _card(self, row: int):
        item = self.queue.item(row)
        return self.queue.itemWidget(item) if item else None

    def _row_of_card(self, card) -> int:
        for row in range(self.queue.count()):
            if self._card(row) is card:
                return row
        return -1

    def status_text(self, row: int) -> str:
        card = self._card(row)
        return card.status_text() if card else ""

    def _items(self):
        return [self.queue.item(r).data(ITEM_ROLE)
                for r in range(self.queue.count())]

    def _row_duration(self, row: int):
        item = self.queue.item(row)
        return item.data(DURATION_ROLE) if item else None

    def _card_meta(self, item: QueueItem) -> str:
        where = item.url if item.kind == "url" else str(item.path)
        tag = {"ru": " · RU", "en": " · EN"}.get(
            getattr(item, "lang_profile", "auto"), "")
        return f"{fmt_duration(item.duration)}{tag} · {where}"

    def _build_card(self, list_item) -> QueueCard:
        """Create a card entirely from the item's data roles (used on
        insert and to resurrect cards after drag-reorders)."""
        item = list_item.data(ITEM_ROLE)
        glyph = "♪" if (item.kind == "file" and item.path.suffix.lower()
                        in thumbs.AUDIO_EXTS) else "▶"
        card = QueueCard(list_item.data(TITLE_ROLE) or item.display_name,
                         list_item.data(META_ROLE) or "", glyph=glyph)
        status = list_item.data(STATUS_ROLE) or tr("queued")
        card.set_status(status, state=list_item.data(STATE_ROLE))
        thumb = list_item.data(THUMB_ROLE)
        if thumb and Path(thumb).exists():
            card.set_thumb(thumb)
        review = list_item.data(REVIEW_ROLE)
        out = list_item.data(OUTPUT_ROLE)
        done = status.startswith(tr("done"))
        card.set_actions(
            review=done and bool(review and Path(review).exists()),
            open_=done and bool(out and Path(out).exists()),
            retry=status.startswith("error"))
        card.review_clicked.connect(
            lambda c=card: self._card_review(self._row_of_card(c)))
        card.open_clicked.connect(
            lambda c=card: self._card_open(self._row_of_card(c)))
        card.retry_clicked.connect(
            lambda c=card: self._card_retry(self._row_of_card(c)))
        card.menu_clicked.connect(
            lambda button, c=card: self._card_menu(
                self._row_of_card(c),
                button.mapToGlobal(button.rect().bottomLeft())))
        return card

    def _restore_cards(self):
        for row in range(self.queue.count()):
            list_item = self.queue.item(row)
            if self.queue.itemWidget(list_item) is None:
                self.queue.setItemWidget(list_item,
                                         self._build_card(list_item))
        self.queue.sync_sizes()
        self._mirror_selection()

    def _move_queue_row(self, src: int, dst: int):
        """Drop handler for the animated reorder: move the grabbed card
        — or the whole selected block when it is part of a
        multi-selection (parity with the old native drag) — then
        rebuild (takeItem destroys the moved items' card widgets)."""
        count = self.queue.count()
        if not (0 <= src < count and 0 <= dst < count) or src == dst:
            return
        rows = sorted(self.queue.row(i) for i in self.queue.selectedItems())
        if src not in rows:
            rows = [src]
        # dst counts positions among all items minus the dragged one;
        # discount the other moving rows that sat above the landing slot
        insert_at = dst - sum(
            1 for r in rows
            if r != src and (r if r < src else r - 1) < dst)
        taken = [self.queue.takeItem(r) for r in reversed(rows)]
        taken.reverse()     # original relative order
        insert_at = max(0, min(insert_at, self.queue.count()))
        for offset, it in enumerate(taken):
            self.queue.insertItem(insert_at + offset, it)
        self._restore_cards()
        for it in taken:
            it.setSelected(True)
        from PySide6.QtCore import QItemSelectionModel
        self.queue.setCurrentItem(
            self.queue.item(insert_at + rows.index(src)),
            QItemSelectionModel.NoUpdate)
        self._mirror_selection()

    def _insert_row(self, item: QueueItem, status: str = None,
                    defer_media: bool = False):
        if status is None:
            status = tr("queued")
        thumb = None
        if item.kind == "file" and not defer_media:
            thumb = thumbs.thumbnail_path(item.path)
        list_item = QListWidgetItem()
        list_item.setData(ITEM_ROLE, item)
        list_item.setData(DURATION_ROLE, item.duration)
        list_item.setData(TITLE_ROLE, item.display_name)
        list_item.setData(META_ROLE, self._card_meta(item))
        list_item.setData(THUMB_ROLE, str(thumb) if thumb else "")
        list_item.setData(STATUS_ROLE, status)
        self.queue.addItem(list_item)
        self.queue.setItemWidget(list_item, self._build_card(list_item))
        self.queue.sync_sizes()
        self._update_queue_stack()

    def _add_files(self, paths):
        existing = {it.path for it in self._items() if it.kind == "file"}
        new_paths = []
        for p in expand_inputs(paths):
            if p not in existing:
                existing.add(p)
                new_paths.append(p)
        # single adds probe inline (fast); bulk adds defer the ffprobe
        # and thumbnail work to a background worker per file
        bulk = len(new_paths) > 1
        for p in new_paths:
            item = QueueItem(kind="file", path=p,
                             duration=None if bulk else media_duration(p))
            self._insert_row(item, defer_media=bulk)
            if bulk:
                card = self._card(self.queue.count() - 1)
                if card:
                    card.set_loading(True)
                self._probe_in_background(item)

    def _probe_in_background(self, item: QueueItem):
        if os.environ.get("WORDMUTE_SYNC_PROBE"):  # tests: no threads
            thumb = thumbs.thumbnail_path(item.path)
            self._on_media_probed(item, media_duration(item.path),
                                  str(thumb) if thumb else "")
            return
        if self._probe_worker is None:
            self._probe_worker = MediaProbeWorker(self)
            self._probe_worker.ready.connect(self._on_media_probed)
            self._probe_worker.start()
        self._probe_worker.enqueue(item)

    def _row_of_item(self, item: QueueItem) -> int:
        for row in range(self.queue.count()):
            if self.queue.item(row).data(ITEM_ROLE) is item:
                return row
        return -1

    def _on_media_probed(self, item: QueueItem, duration, thumb: str):
        row = self._row_of_item(item)
        if row < 0:
            return          # removed from the queue meanwhile
        item.duration = duration
        list_item = self.queue.item(row)
        list_item.setData(DURATION_ROLE, duration)
        list_item.setData(META_ROLE, self._card_meta(item))
        if thumb:
            list_item.setData(THUMB_ROLE, thumb)
        card = self._card(row)
        if card:
            card.set_loading(False)
            card.set_meta(self._card_meta(item))
            if thumb:
                card.set_thumb(thumb)

    def _add_url_row(self, item: QueueItem):
        self._insert_row(item,
                         status=f"{tr('queued')} ({item.format_label})")

    def _add_url(self, url: str = ""):
        if not isinstance(url, str):  # a stray signal bool must never win
            url = ""
        dialog = AddUrlDialog(self, url=url,
                              cookies=self._settings.get("cookies_file")
                              or None,
                              quality=self._settings.get("batch_quality"))
        if dialog.exec():
            for item in dialog.result_items():
                self._add_url_row(item)
            # remember the batch quality cap for next time
            chosen = dialog.quality()
            if chosen and chosen != self._settings.get("batch_quality"):
                self._settings["batch_quality"] = chosen
                config.save_settings(self._settings)

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
        for row in sorted({self.queue.row(i)
                           for i in self.queue.selectedItems()},
                          reverse=True):
            self.queue.takeItem(row)
        self._update_queue_stack()

    def _mirror_selection(self):
        # QSS can't style an item widget from its item's selection state
        for row in range(self.queue.count()):
            card = self._card(row)
            if card:
                card.set_selected(self.queue.item(row).isSelected())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        self._add_files(u.toLocalFile() for u in mime.urls()
                        if u.isLocalFile())
        web = [u.toString() for u in mime.urls()
               if u.scheme() in ("http", "https")]
        if not web and mime.hasText():
            from .url_dialog import extract_urls
            web = extract_urls(mime.text())
        if len(web) > 1:
            # several links dropped: queue them all at the remembered
            # batch quality cap (same rule as the Add URL dialog)
            from ..core import downloader
            spec, label = downloader.quality_spec(
                self._settings.get("batch_quality",
                                   downloader.DEFAULT_QUALITY))
            for u in web:
                self._add_url_row(QueueItem(
                    kind="url", url=u, format_spec=spec,
                    format_label=label))
        elif web:
            self._add_url(web[0])

    # ---------------------------------------------------------- row context
    def _review_path_for_row(self, row: int):
        item = self.queue.item(row)
        return item.data(REVIEW_ROLE) if item else None

    def _output_path_for_row(self, row: int):
        item = self.queue.item(row)
        return item.data(OUTPUT_ROLE) if item else None

    def _card_review(self, row: int):
        path = self._review_path_for_row(row)
        if path and Path(path).exists():
            self._open_review(path)

    def _card_open(self, row: int):
        out = self._output_path_for_row(row)
        if out and Path(out).exists():
            os.startfile(out)

    def _card_retry(self, row: int):
        card = self._card(row)
        if card is None or self._worker is not None:
            return
        self._apply_status(row, tr("queued"))
        card.set_actions()

    def _build_card_menu(self, row: int):
        """(menu, actions) for the card ⋯ menu — split out of
        _card_menu so it can be built without exec()ing it (tests and
        the screenshot script)."""
        menu = themed_menu(self, "card_menu")
        out = self._output_path_for_row(row)
        out_ok = bool(out and Path(out).exists())
        act_open = menu.addAction(tr("Open output"))
        act_open.setEnabled(out_ok)
        act_show = menu.addAction(tr("Show output in folder"))
        act_show.setEnabled(out_ok)
        rev = self._review_path_for_row(row)
        act_review = menu.addAction(tr("Review"))
        act_review.setEnabled(bool(rev and Path(rev).exists()))
        menu.addSeparator()
        # per-item language: force the RU/EN list+plan for this video
        row_item = self.queue.item(row)
        queue_obj = row_item.data(ITEM_ROLE) if row_item else None
        lang_menu = themed_menu(menu, "card_menu_language")
        lang_menu.setTitle(tr("Processing language"))
        menu.addMenu(lang_menu)
        # addMenu hands ownership to Python: without a reference the
        # submenu is collected as soon as the builder returns
        menu._lang_menu = lang_menu
        current = getattr(queue_obj, "lang_profile", "auto") or "auto"
        for key, label in (("auto", tr("Auto (main setup)")),
                           ("ru", tr("Russian")),
                           ("en", tr("English"))):
            act = lang_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(key == current)
            act.triggered.connect(
                lambda _=False, k=key, r=row: self._set_item_lang(r, k))
        menu.addSeparator()
        deletable = self._worker is None
        # short labels: the confirmation lists the exact files anyway
        act_del_src = menu.addAction(tr("Delete source and JSONs"))
        act_del_src.setEnabled(
            deletable and bool(self._files_for_row(row, False)))
        mark_danger(act_del_src)
        act_del_all = menu.addAction(tr("Delete all files"))
        act_del_all.setEnabled(
            deletable and bool(self._files_for_row(row, True)))
        mark_danger(act_del_all)
        menu.addSeparator()
        act_remove = menu.addAction(tr("Remove"))
        act_remove.setEnabled(deletable)
        return menu, {"open": act_open, "show": act_show,
                      "review": act_review, "del_src": act_del_src,
                      "del_all": act_del_all, "remove": act_remove,
                      "out": out, "rev": rev}

    def _card_menu(self, row: int, global_pos):
        if row < 0:
            return
        menu, acts = self._build_card_menu(row)
        act_open, act_show = acts["open"], acts["show"]
        act_review = acts["review"]
        act_del_src, act_del_all = acts["del_src"], acts["del_all"]
        act_remove = acts["remove"]
        out, rev = acts["out"], acts["rev"]
        chosen = menu.exec(global_pos)
        if chosen is act_open:
            os.startfile(out)
        elif chosen is act_show:
            import subprocess
            subprocess.Popen(["explorer", "/select,", str(Path(out))])
        elif chosen is act_review:
            self._open_review(rev)
        elif chosen is act_del_src:
            self._delete_row_files(row, include_output=False)
        elif chosen is act_del_all:
            self._delete_row_files(row, include_output=True)
        elif chosen is act_remove:
            self.queue.takeItem(row)
            self._update_queue_stack()

    def _set_item_lang(self, row: int, profile: str):
        list_item = self.queue.item(row)
        if list_item is None:
            return
        item = list_item.data(ITEM_ROLE)
        item.lang_profile = profile
        meta = self._card_meta(item)
        list_item.setData(META_ROLE, meta)
        card = self._card(row)
        if card:
            card.set_meta(meta)

    def _files_for_row(self, row: int, include_output: bool) -> list:
        from ..core import cleanup
        item = self.queue.item(row)
        queue_item = item.data(ITEM_ROLE) if item else None
        out = self._output_path_for_row(row)
        fallback = (queue_item.path if queue_item
                    and queue_item.kind == "file" else None)
        source = cleanup.resolve_source(output=out, fallback=fallback)
        return cleanup.related_files(source=source, output=out,
                                     include_output=include_output)

    def _delete_row_files(self, row: int, include_output: bool):
        from .file_delete import confirm_and_recycle
        if confirm_and_recycle(self, self._files_for_row(row,
                                                         include_output)):
            if include_output:  # output gone -> review/open are dead ends
                item = self.queue.item(row)
                if item:
                    item.setData(OUTPUT_ROLE, None)
                    item.setData(REVIEW_ROLE, None)
                    card = self._card(row)
                    if card:
                        card.set_actions()
                    self._apply_status(row, tr("files deleted"))

    def _open_review(self, path):
        # non-modal: the queue stays visible/alive while reviewing
        dialog = ReviewDialog(path, self)
        dialog.setWindowModality(Qt.NonModal)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        self._review_windows.append(dialog)
        dialog.destroyed.connect(
            lambda *_: self._review_windows.remove(dialog)
            if dialog in self._review_windows else None)
        dialog.show()

    def _on_row_double_clicked(self, item):
        path = self._review_path_for_row(self.queue.row(item))
        if path and Path(path).exists():
            self._open_review(path)
        else:
            inform(self, title=tr("Nothing to review yet"),
                   body=tr("Review data appears after the file has been "
                           "processed and something was muted."))

    def _pick_review(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open review file", "",
            "WordMute review (*.wordmute.json);;All files (*)")
        if path:
            try:
                self._open_review(path)
            except Exception as exc:
                inform(self, title=tr("Could not open the review file"),
                       body=str(exc))

    # ---------------------------------------------------------- warnings
    @staticmethod
    def _gigaam_installed() -> bool:
        """Either backend counts: onnx-asr (what setup installs) or the
        legacy torch gigaam package."""
        import importlib.util
        try:
            return any(importlib.util.find_spec(name) is not None
                       for name in ("onnx_asr", "gigaam"))
        except (ImportError, ValueError):
            return False

    def _current_warnings(self) -> list:
        s = self._settings
        engines = self.plan.engines()
        plan = build_plan(engines, s["model"], s["gigaam_model"])
        warnings = gpu.plan_warnings(plan, s["device"], self._gpus)
        if "gigaam" in engines and not self._gigaam_installed():
            warnings.append(
                tr("GigaAM is not installed — add it in Models → "
                   "Components, or use Whisper passes instead."))
        return warnings

    def _refresh_warnings(self):
        warnings = self._current_warnings()
        self.warnings_label.setText("\n".join(f"⚠ {w}" for w in warnings))
        self.warnings_label.setVisible(bool(warnings))
        severe = any("will fail" in w for w in warnings)
        if self.warnings_label.property("severity") != \
                ("error" if severe else None):
            self.warnings_label.setProperty(
                "severity", "error" if severe else None)
            style = self.warnings_label.style()
            style.unpolish(self.warnings_label)
            style.polish(self.warnings_label)

    # ---------------------------------------------------------- run
    def _pick_gigaam_backend(self, settings) -> str:
        """torch on a working CUDA GPU is still by far the fastest
        GigaAM path; onnx-asr wins everywhere else (fast on plain CPU,
        no HF account). Settings "gigaam_backend" forces either one.
        find_spec avoids importing torch/onnxruntime just to choose."""
        from importlib.util import find_spec

        forced = settings.get("gigaam_backend", "auto")
        if forced in ("torch", "onnx"):
            return forced
        has_torch = find_spec("gigaam") is not None
        has_onnx = find_spec("onnx_asr") is not None
        if has_torch and settings.get("device") == "cuda" and self._gpus:
            return "torch"          # GPU: torch is much faster
        if has_onnx:
            return "onnx"
        return "torch"

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

    def _pending_rows(self) -> list:
        """Rows Start should process: still queued, or cancelled from an
        interrupted batch. Done/error rows stay untouched (Retry
        re-queues an error explicitly)."""
        rows = []
        for r in range(self.queue.count()):
            status = self.status_text(r)
            if status.startswith(tr("queued")) or status == tr("cancelled"):
                rows.append(r)
        return rows

    def _start(self, auto: bool = False):
        # a drag in flight (possible when the watch timer auto-starts)
        # must finish before rows are cleared/captured, or the worker's
        # row mapping desyncs from the queue
        self._queue_reorder.abort()
        if auto:
            # watch-folder runs: keep only still-queued rows so earlier
            # results are never reprocessed
            self._clear_finished_rows()
        if not self.queue.count():
            if not auto:
                inform(self, title=tr("Add some files first."))
            return
        pending = self._pending_rows()
        if not pending:
            if not auto:
                inform(self, title=tr("Everything is processed already"),
                       body=tr("Add new files, or use Retry on a failed "
                               "one."))
            return
        items = [self.queue.item(r).data(ITEM_ROLE) for r in pending]
        lists = self._selected_wordlists()
        if not lists:
            if not auto:
                inform(self, title=tr("Select at least one word list."))
            return
        engines = self.plan.engines()
        if not engines:
            if not auto:
                inform(self, title=tr("Add at least one pass to the "
                                      "plan."))
            return
        gigaam_backend = self._pick_gigaam_backend(self._settings)
        # No Hugging Face account is needed any more: setup installs
        # GigaAM through onnx-asr. A token file left over from the old
        # torch path is still honoured, since that path (dev installs
        # with the gigaam package) reads it for the gated pyannote VAD.
        saved_token = config.load_hf_token()
        if saved_token:
            os.environ["HF_TOKEN"] = saved_token

        wordlist = merge_wordlists(lists)
        s = self._settings
        # engine-level toggles, captured at Start like the options below
        from ..engine import wordmute as engine_mod
        engine_mod.configure_fast_mode(s.get("fast_mode", False))
        engine_mod.configure_gigaam_backend(gigaam_backend)
        options = JobOptions(
            device=s["device"], language=s["language"], pad=s["pad_ms"],
            no_vad=not s["vad"],
            retranscribe=self.retranscribe_check.isChecked(),
            force_passes=self.force_passes_check.isChecked(),
            beep_hz=s.get("beep_hz", 0) or None,
        )
        plan = build_plan(engines, s["model"], s["gigaam_model"])
        # per-item RU/EN profiles: both lists load regardless of the
        # global checkboxes, so one queue can mix languages (card ⋮
        # menu → «Язык обработки»). GigaAM can't do English, so the
        # EN plan converts its passes to whisper, keeping the count.
        profiles = {
            "ru": (merge_wordlists([self._wordlist_paths["russian"]]),
                   plan, "ru"),
            "en": (merge_wordlists([self._wordlist_paths["english"]]),
                   [("whisper", s["model"]) for _ in plan], "en"),
        }
        output_dir = (Path(s["output_dir"])
                      if s["output_mode"] == "folder" and s["output_dir"]
                      else None)

        for row in pending:
            self._apply_status(row, tr("queued"))
            card = self._card(row)
            if card:
                card.set_actions()

        self._active_rows = pending
        self._reset_run_state(total=len(items))
        self._pass_total = len(plan)
        self._worker = ProcessWorker(items, wordlist, plan, options,
                                     output_dir=output_dir,
                                     download_dir=config.download_dir(s),
                                     cookies=s.get("cookies_file") or None,
                                     profiles=profiles)
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
            self.status_label.setText(tr("Cancelling…"))
            self.cancel_button.setEnabled(False)

    def _set_running(self, running: bool):
        # long batches must survive the Windows sleep timer
        from ..core import power
        power.keep_awake(running)
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.add_button.setEnabled(not running)
        self.add_folder_button.setEnabled(not running)
        self.add_url_button.setEnabled(not running)
        self.remove_button.setEnabled(not running)
        # reordering mid-run would desync the worker's row mapping
        self.queue.setProperty("reorder_enabled", not running)
        # settings tab stays enabled: options are captured at Start, so
        # edits only affect the next run
        for w in (self.russian_check, self.english_check, self.plan,
                  self.force_passes_check, self.retranscribe_check):
            w.setEnabled(not running)
        if running:
            self.progress_bar.setRange(0, self._total_files * 100)
            self.progress_bar.setValue(0)
            self.percent_label.setText("0%")
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.percent_label.setText("")
            self.tabs.setTabText(0, tr("Queue"))

    # ---------------------------------------------------------- progress
    def _update_overall_progress(self):
        if not self._total_files:
            return
        pass_fraction = ((self._pass_n - 1) + min(self._pass_pct, 1.0)) \
            / max(self._pass_total, 1)
        value = self._done_files * 100 + int(min(pass_fraction, 0.99) * 100)
        self.progress_bar.setValue(value)
        pct = int(value / (self._total_files * 100) * 100)
        self.percent_label.setText(f"{pct}%")
        # progress stays visible from any tab
        self.tabs.setTabText(0, f"{tr('Queue')} · {pct}%")

    def _set_row_status(self, text: str, state=None, progress=None):
        if self._current_row is not None:
            self._apply_status(self._current_row, text, state=state,
                               progress=progress)

    def _apply_status(self, row: int, text: str, state=None,
                      progress=None):
        card = self._card(row)
        if card:
            card.set_status(text, state=state, progress=progress)
        list_item = self.queue.item(row)
        if list_item:  # keep roles in sync for drag-rebuilds
            list_item.setData(STATUS_ROLE, text)
            list_item.setData(STATE_ROLE, state)

    def _pass_prefix(self) -> str:
        if self._pass_total > 1:
            return f"pass {self._pass_n}/{self._pass_total} · "
        return ""

    # ---------------------------------------------------------- worker events
    def _append_log(self, text: str):
        self.log.appendPlainText(text)

    def _on_engine_event(self, event: str, data: dict):
        if event == "download_start":
            row = self._map_row(data.get("row", 0))
            self._apply_status(row, tr("downloading") + "…")
            # a prefetch download must not hijack the global status line
            if row == self._current_row:
                self.status_label.setText(
                    tr("Downloading {}…").format(data["url"]))
        elif event == "download_progress":
            self._on_download_progress(data)
            return
        elif event == "download_done":
            self._on_download_done(data["path"],
                                   self._map_row(data.get("row", 0)))
        elif event == "review_saved":
            if self._current_row is not None:
                self.queue.item(self._current_row).setData(
                    REVIEW_ROLE, data["path"])
        elif event == "item_output":
            if self._current_row is not None:
                self.queue.item(self._current_row).setData(
                    OUTPUT_ROLE, data["path"])
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
            self._set_row_status(f"{self._pass_prefix()}{tr('muting…')}")
        elif event == "mute_progress":
            self._on_mute_progress(data["seconds"])
            return

        line = format_event(event, data)
        if line:
            self._append_log(line)

    def _on_download_progress(self, d: dict):
        downloaded, total = d.get("downloaded"), d.get("total")
        parts = []
        pct = None
        if downloaded and total:
            pct = downloaded / total
            parts.append(f"{tr('downloading')} {pct:.0%}")
        elif downloaded:
            parts.append(f"{tr('downloading')} "
                         f"{downloaded / (1024 * 1024):.0f} MB")
        else:
            parts.append(tr("downloading"))
        speed = fmt_speed(d.get("speed"))
        if speed:
            parts.append(speed)
        if d.get("eta"):
            parts.append(fmt_eta(d["eta"]))
        self._apply_status(self._map_row(d.get("row", 0)),
                           " · ".join(parts), progress=pct)

    def _on_download_done(self, path: str, row: int):
        # the file is now local: show its real name, duration and
        # thumbnail so the card behaves like any local file's
        list_item = self.queue.item(row)
        if list_item is None:
            return
        p = Path(path)
        duration = media_duration(p)
        meta = f"{fmt_duration(duration)} · {p}"
        thumb = thumbs.thumbnail_path(p)
        list_item.setData(DURATION_ROLE, duration)
        list_item.setData(TITLE_ROLE, p.name)
        list_item.setData(META_ROLE, meta)
        list_item.setData(THUMB_ROLE, str(thumb) if thumb else "")
        card = self._card(row)
        if card:
            card.set_title(p.name)
            card.set_meta(meta)
            if thumb:
                card.set_thumb(thumb)
        if row != self._current_row:  # prefetched: waiting for its turn
            self._apply_status(row, tr("downloaded · waiting"))

    def _on_mute_progress(self, seconds: float):
        duration = (self._row_duration(self._current_row)
                    if self._current_row is not None else None)
        if duration:
            pct = min(seconds / duration, 1.0)
            text = f"{self._pass_prefix()}{tr('muting…')} {pct:.0%}"
            self._set_row_status(text, progress=pct)
        else:
            text = f"{self._pass_prefix()}{tr('muting…')} {fmt_hms(seconds)}"
            self._set_row_status(text)

    def _on_asr_progress(self, minutes: float):
        processed = minutes * 60
        duration = (self._row_duration(self._current_row)
                    if self._current_row is not None else None)
        pct = None
        if duration:
            pct = min(processed / duration, 1.0)
            self._pass_pct = 0.9 * pct  # transcription ~= the whole pass
            text = f"{self._pass_prefix()}{tr('transcribing')} {pct:.0%}"
            if self._asr_wall_start and pct > 0.02:
                elapsed = time.monotonic() - self._asr_wall_start
                speed = processed / elapsed
                if speed > 0:
                    text += f" · {fmt_eta((duration - processed) / speed)}"
        else:
            text = (f"{self._pass_prefix()}{tr('transcribing')} "
                    f"{fmt_hms(processed)}")
        self._set_row_status(text, progress=pct)
        self.status_label.setText(
            tr("Transcribing… {} of audio processed")
            .format(fmt_hms(processed)))
        self._update_overall_progress()

    def _map_row(self, index: int) -> int:
        """Worker indexes count only the items of this run; map them to
        actual queue rows (done rows are skipped by Start)."""
        if 0 <= index < len(self._active_rows):
            return self._active_rows[index]
        return index

    def _on_file_started(self, row: int, name: str):
        row = self._map_row(row)
        self._current_row = row
        self._pass_n = 1
        self._pass_pct = 0.0
        self._asr_wall_start = None
        self._set_row_status(tr("processing…"))
        self.status_label.setText(tr("Processing {}…").format(name))
        self._append_log(f"\n=== {name} ===")

    def _on_file_finished(self, row: int, ok: bool, error: str):
        row = self._map_row(row)
        self._done_files += 1
        self._pass_pct = 0.0
        card = self._card(row)
        out = self._output_path_for_row(row)
        has_out = bool(out and Path(out).exists())
        has_review = bool(self._review_path_for_row(row))
        if ok:
            text = tr("done")
            if out:
                text += f" → {Path(out).name}"
            state = "ok"
        else:
            text = (tr("cancelled") if error == "cancelled"
                    else f"error: {error}")
            state = None if error == "cancelled" else "err"
        self._apply_status(row, text, state=state)
        if card:
            card.set_actions(review=ok and has_review,
                             open_=ok and has_out,
                             retry=not ok and error != "cancelled")
        if ok and self.isActiveWindow():
            from .toasts import show_toast
            item = self.queue.item(row)
            title = (item.data(TITLE_ROLE) if item else "") or ""
            show_toast(self, tr("Done"),
                       Path(out).name if out else title)
        if not ok and error != "cancelled":
            self._append_log(f"Error: {error}")
        self._update_overall_progress()

    def _on_all_finished(self, done: int, total: int):
        self._worker = None
        self._set_running(False)
        summary = tr("Finished: {}/{} file(s) ok.").format(done, total)
        self.status_label.setText(summary)
        self._append_log("\n" + summary)
        self._notify_finished(summary)

    def _on_tray_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _notify_finished(self, summary: str):
        """Active window gets an in-app toast; a backgrounded one gets
        the taskbar flash + tray balloon."""
        if self.isActiveWindow():
            from .toasts import show_toast
            show_toast(self, summary, duration_ms=7000)
            return
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon
        QApplication.alert(self)
        if self._tray is not None:
            self._tray.showMessage("WordMute", summary,
                                   QSystemTrayIcon.Information, 8000)

    # ------------------------------------------------------ app updates
    def _start_update_check(self):
        """Quiet startup check against GitHub releases; silent unless a
        newer version exists. Opt out: "check_app_updates": false in
        settings.json."""
        if (self._app_update_worker is not None
                or os.environ.get("WORDMUTE_NO_UPDATE_CHECK")
                or not self._settings.get("check_app_updates", True)):
            return
        self._app_update_worker = AppUpdateWorker()
        self._app_update_worker.result.connect(self._on_app_update_result)
        self._app_update_worker.start()

    def _on_app_update_result(self, info: dict):
        if not info.get("update"):
            return
        self._update_url = info["url"]
        line = tr("New WordMute version available: {} (you have {})") \
            .format(info["latest"], info["current"])
        self._append_log(line + f" — {info['url']}")
        if self._tray is not None:
            from PySide6.QtWidgets import QSystemTrayIcon
            try:
                self._tray.messageClicked.disconnect(self._open_update_page)
            except (TypeError, RuntimeError):
                pass
            self._tray.messageClicked.connect(self._open_update_page)
            self._tray.showMessage(
                "WordMute", line + "\n"
                + tr("Click to open the download page."),
                QSystemTrayIcon.Information, 10000)

    def _open_update_page(self):
        if getattr(self, "_update_url", None):
            import webbrowser
            webbrowser.open(self._update_url)
            self._update_url = None

    # ---------------------------------------------------------- lifecycle
    def closeEvent(self, event):
        if self._worker is not None:
            if not confirm(self,
                           title=tr("Processing is still running."),
                           body=tr("Quitting cancels the current file; "
                                   "finished files are kept."),
                           ok_text=tr("Cancel and quit")):
                event.ignore()
                return
            self._worker.cancel()
            self._worker.wait(15000)
        if not self.wordlists_tab.maybe_save():
            event.ignore()
            return
        self.models_tab.shutdown()
        if self._app_update_worker is not None:
            self._app_update_worker.wait(5000)
        if self._probe_worker is not None:
            self._probe_worker.stop()
            self._probe_worker.wait(10000)
        self._settings.update({
            "use_russian": self.russian_check.isChecked(),
            "use_english": self.english_check.isChecked(),
            "plan": self.plan.engines(),
            "force_passes": self.force_passes_check.isChecked(),
        })
        config.save_settings(self._settings)
        event.accept()
