"""Add-URL dialog: paste a link, optionally fetch yt-dlp's format list
and pick a specific quality, or add straight away at best quality."""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core import downloader
from ..core.jobs import QueueItem
from .i18n import tr

# keep fetch threads alive if their dialog closes early; Qt drops the
# signal connections with the dialog, so late emits are harmless
_live_workers = set()


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
    COLUMNS = ["Quality", "Ext", "FPS", "Type", "Size", "Note"]

    def __init__(self, parent=None, url: str = "", cookies=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Add URL"))
        self.resize(640, 480)
        self._info = None
        self._use_best = False
        self._cookies = cookies

        layout = QVBoxLayout(self)
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit(url)
        self.url_edit.setPlaceholderText("https://…")
        self.fetch_button = QPushButton(tr("Fetch formats"))
        self.fetch_button.clicked.connect(self._fetch)
        url_row.addWidget(self.url_edit, stretch=1)
        url_row.addWidget(self.fetch_button)
        layout.addLayout(url_row)

        self.status = QLabel(tr("Paste a video URL, then either fetch the "
                                "format list or add it at best quality."))
        self.status.setWordWrap(True)
        self.status.setProperty("muted", True)
        layout.addWidget(self.status)

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

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [tr(c) for c in self.COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(lambda _: self.accept())
        self.table.itemSelectionChanged.connect(self._update_ok)
        layout.addWidget(self.table, stretch=1)

        buttons_row = QHBoxLayout()
        self.best_button = QPushButton(tr("Add (best quality)"))
        self.best_button.setProperty("primary", True)
        self.best_button.setToolTip(
            "Skip the format list and download best video+audio.")
        self.best_button.clicked.connect(self._accept_best)
        buttons_row.addWidget(self.best_button)
        buttons_row.addStretch()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(tr("Add selected"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        buttons_row.addWidget(self.buttons)
        layout.addLayout(buttons_row)
        self._update_ok()

    def _goto_settings(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, "tabs") \
                and hasattr(parent, "settings_tab"):
            parent.tabs.setCurrentWidget(parent.settings_tab)
        self.reject()

    # ---------------------------------------------------------- fetching
    def _url(self) -> str:
        return self.url_edit.text().strip()

    def _fetch(self):
        url = self._url()
        if not url:
            return
        self.fetch_button.setEnabled(False)
        self.status.setText(tr("Fetching format list…"))
        worker = FormatListWorker(url, cookies=self._cookies)
        worker.ready.connect(self._on_formats_ready)
        worker.error.connect(self._on_fetch_error)
        worker.start()

    def _on_formats_ready(self, info: dict):
        self._info = info
        self.fetch_button.setEnabled(True)
        duration = info.get("duration")
        extra = f" · {int(duration // 60)} min" if duration else ""
        self.status.setText(f"{info['title']}{extra}")
        self.table.setRowCount(0)
        self._add_row([tr("Best video+audio (recommended)"),
                       "", "", "", "", ""], None)
        for f in info["formats"]:
            d = downloader.describe_format(f)
            self._add_row(
                [d["resolution"] or d["id"], d["ext"],
                 str(int(d["fps"])) if d["fps"] else "",
                 d["kind"], d["size"], d["note"]],
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
            self.table.setItem(row, col, item)

    def _on_fetch_error(self, message: str):
        self.fetch_button.setEnabled(True)
        self.status.setText(
            tr("Could not fetch formats: {}").format(message))

    def _update_ok(self):
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.table.selectionModel()
                 and self.table.selectionModel().hasSelection()))

    # ---------------------------------------------------------- result
    def _accept_best(self):
        if not self._url():
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
