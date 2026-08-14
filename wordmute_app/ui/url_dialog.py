"""Add-URL dialog: paste a link, optionally fetch yt-dlp's format list
and pick a specific quality, or add straight away at best quality.
Pasting SEVERAL links at once switches to batch mode: all of them are
added at best quality in one go."""

import re

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import downloader
from ..core.jobs import QueueItem
from .hover_table import HoverRowTable
from .i18n import tr

# keep fetch threads alive if their dialog closes early; Qt drops the
# signal connections with the dialog, so late emits are harmless
_live_workers = set()

# a URL runs until whitespace/comma/semicolon OR the next http(s)://
# — QLineEdit may join pasted lines with nothing in between
_URL_RE = re.compile(r"https?://(?:(?!https?://)[^\s,;])+")


def extract_urls(text: str) -> list:
    """Every distinct http(s) link in the text, in order."""
    seen = []
    for url in _URL_RE.findall(text or ""):
        if url not in seen:
            seen.append(url)
    return seen


class FormatListWorker(QThread):
    ready = Signal(dict)
    error = Signal(str)

    def __init__(self, url: str, cookies=None):
        super().__init__()
        self._url = url
        self._cookies = cookies
        _live_workers.add(self)
        self.finished.connect(lambda: _live_workers.discard(self))

    def run(self):
        try:
            self.ready.emit(
                downloader.list_formats(self._url, cookies=self._cookies))
        except Exception as exc:
            self.error.emit(str(exc))


class AddUrlDialog(QDialog):
    COLUMNS = ["Quality", "Size", "Note", "Ext", "FPS", "Type"]

    def __init__(self, parent=None, url: str = "", cookies=None,
                 auto_fetch: bool = True, quality: str = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Add URL"))
        self.resize(780, 560)
        self.setMinimumWidth(720)
        self._info = None
        self._use_best = False
        self._cookies = cookies
        self._fetch_generation = 0
        self._multi_urls = []

        layout = QVBoxLayout(self)
        self.url_edit = QLineEdit(url)
        self.url_edit.setPlaceholderText("https://…")
        # formats load automatically: debounce typing, Enter = right now
        self._fetch_timer = QTimer(self)
        self._fetch_timer.setSingleShot(True)
        self._fetch_timer.setInterval(800)
        self._fetch_timer.timeout.connect(self._fetch)
        self.url_edit.textChanged.connect(self._schedule_fetch)
        self.url_edit.returnPressed.connect(self._fetch)
        layout.addWidget(self.url_edit)

        self.status = QLabel(tr("Paste a video URL — the format list "
                                "loads automatically."))
        self.status.setWordWrap(True)
        self.status.setProperty("muted", True)
        layout.addWidget(self.status)

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)  # indeterminate
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setVisible(False)
        layout.addWidget(self.loading_bar)

        # batch mode has no per-link format table — one quality cap for
        # the whole batch instead of silently grabbing 4K
        self.quality_row = QWidget()
        quality_layout = QHBoxLayout(self.quality_row)
        quality_layout.setContentsMargins(0, 0, 0, 0)
        quality_layout.setSpacing(8)
        quality_layout.addWidget(QLabel(tr("Quality for all links:")))
        self.quality_combo = QComboBox()
        for key, label, _spec in downloader.QUALITY_PRESETS:
            self.quality_combo.addItem(tr(label), key)
        preset = (quality if quality in
                  [k for k, _, _ in downloader.QUALITY_PRESETS]
                  else downloader.DEFAULT_QUALITY)
        self.quality_combo.setCurrentIndex(
            self.quality_combo.findData(preset))
        self.quality_combo.currentIndexChanged.connect(
            lambda _: self._update_multi_labels())
        quality_layout.addWidget(self.quality_combo)
        quality_layout.addStretch()
        self.quality_row.setVisible(False)
        layout.addWidget(self.quality_row)

        if not self._cookies:
            cookies_row = QHBoxLayout()
            self.cookies_hint = QLabel(tr(
                "Members-only sites (e.g. Boosty) may need your cookies "
                "file —"))
            self.cookies_hint.setProperty("muted", True)
            cookies_link = QPushButton(tr("set it in Settings"))
            cookies_link.setFlat(True)
            cookies_link.clicked.connect(self._goto_settings)
            cookies_row.addWidget(self.cookies_hint)
            cookies_row.addWidget(cookies_link)
            cookies_row.addStretch()
            layout.addLayout(cookies_row)

        self.table = HoverRowTable(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [tr(c) for c in self.COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(lambda _: self.accept())
        self.table.itemSelectionChanged.connect(self._update_ok)
        layout.addWidget(self.table, stretch=1)

        buttons_row = QHBoxLayout()
        self.best_button = QPushButton(tr("Add (best quality)"))
        self.best_button.setProperty("primary", True)
        self.best_button.setToolTip(
            tr("Skip the format list and download best video+audio."))
        self.best_button.clicked.connect(self._accept_best)
        buttons_row.addWidget(self.best_button)
        buttons_row.addStretch()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(tr("Add selected"))
        self.buttons.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        buttons_row.addWidget(self.buttons)
        layout.addLayout(buttons_row)
        self._update_ok()
        if auto_fetch and self._looks_like_url(url):
            QTimer.singleShot(0, self._fetch)

    def _goto_settings(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, "tabs") \
                and hasattr(parent, "settings_tab"):
            parent.tabs.setCurrentWidget(parent.settings_tab)
        self.reject()

    # ---------------------------------------------------------- fetching
    def _url(self) -> str:
        return self.url_edit.text().strip()

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        return text.strip().startswith(("http://", "https://"))

    def _schedule_fetch(self):
        urls = extract_urls(self.url_edit.text())
        if len(urls) >= 2:
            self._enter_multi_mode(urls)
            return
        if self._multi_urls:
            self._leave_multi_mode()
        if self._looks_like_url(self._url()):
            self._fetch_timer.start()
        else:
            self._fetch_timer.stop()

    def _enter_multi_mode(self, urls):
        """Several links pasted: no per-link format table — one quality
        cap applies to the whole batch."""
        self._fetch_timer.stop()
        self._multi_urls = urls
        self.loading_bar.setVisible(False)
        self.table.setRowCount(0)
        self._info = None
        self.quality_row.setVisible(True)
        self._update_multi_labels()
        self._update_ok()

    def _update_multi_labels(self):
        if not self._multi_urls:
            return
        _spec, label = downloader.quality_spec(self.quality())
        self.status.setText(
            tr("{} links · quality: {}").format(
                len(self._multi_urls), tr(label)))
        self.best_button.setText(
            tr("Add {} links").format(len(self._multi_urls)))

    def quality(self) -> str:
        return self.quality_combo.currentData()

    def _leave_multi_mode(self):
        self._multi_urls = []
        self.quality_row.setVisible(False)
        self.best_button.setText(tr("Add (best quality)"))
        self.status.setText(tr("Paste a video URL — the format list "
                               "loads automatically."))

    def _fetch(self):
        if self._multi_urls:
            return
        url = self._url()
        if not self._looks_like_url(url):
            return
        self._fetch_timer.stop()
        self._fetch_generation += 1
        generation = self._fetch_generation
        self.status.setText(tr("Fetching format list…"))
        self.loading_bar.setVisible(True)
        self.table.setRowCount(0)
        self._info = None
        self._update_ok()
        worker = FormatListWorker(url, cookies=self._cookies)
        # a newer fetch (edited URL) makes this one's result stale
        worker.ready.connect(
            lambda info, g=generation:
            self._on_formats_ready(info)
            if g == self._fetch_generation else None)
        worker.error.connect(
            lambda message, g=generation:
            self._on_fetch_error(message)
            if g == self._fetch_generation else None)
        worker.start()

    def _on_formats_ready(self, info: dict):
        self._info = info
        self.loading_bar.setVisible(False)
        duration = info.get("duration")
        if duration and duration >= 60:
            extra = f" · {int(duration // 60)} {tr('min')}"
        elif duration:
            extra = f" · {int(duration)} {tr('s')}"
        else:
            extra = ""
        self.status.setText(f"{info['title']}{extra}")
        self.table.setRowCount(0)
        self._add_row([tr("Best video+audio\n(recommended)"),
                       "", "", "", "", ""], None)
        self.table.setRowHeight(0, 56)
        for f in info["formats"]:
            d = downloader.describe_format(f, duration=duration)
            self._add_row(
                [d["resolution"] or d["id"], d["size"], d["note"],
                 d["ext"], str(int(d["fps"])) if d["fps"] else "",
                 tr(d["kind"])],
                f)
        self.table.selectRow(0)
        self._update_ok()

    def _add_row(self, texts, fmt):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, text in enumerate(texts):
            item = QTableWidgetItem(text)
            if col == 0:
                item.setData(Qt.UserRole, fmt)
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item)

    def _on_fetch_error(self, message: str):
        self.loading_bar.setVisible(False)
        self.status.setText(
            tr("Could not fetch formats: {}").format(message))

    def _update_ok(self):
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.table.selectionModel()
                 and self.table.selectionModel().hasSelection()))

    # ---------------------------------------------------------- result
    def _accept_best(self):
        if not self._url() and not self._multi_urls:
            return
        self._use_best = True
        self.accept()

    def _selected_format(self):
        rows = self.table.selectionModel().selectedRows() \
            if self.table.selectionModel() else []
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    def result_item(self) -> QueueItem:
        info = self._info or {}
        fmt = None if self._use_best else self._selected_format()
        if fmt is None:
            spec, label = downloader.BEST_SPEC, downloader.BEST_LABEL
        else:
            spec = downloader.spec_for_format(fmt)
            label = downloader.format_label(fmt)
        return QueueItem(
            kind="url",
            url=info.get("url") or self._url(),
            format_spec=spec,
            format_label=label,
            title=info.get("title", ""),
            duration=info.get("duration"),
        )

    def result_items(self) -> list:
        """Batch mode: one item per pasted link at the chosen quality
        cap; otherwise the single (possibly format-picked) item."""
        if self._multi_urls:
            spec, label = downloader.quality_spec(self.quality())
            return [QueueItem(kind="url", url=u, format_spec=spec,
                              format_label=label)
                    for u in self._multi_urls]
        return [self.result_item()]
