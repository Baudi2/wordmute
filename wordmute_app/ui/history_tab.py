"""History tab: log of processed items."""

import os
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import config, history
from .hover_table import HoverRowTable
from .i18n import tr

COLUMNS = ["Time", "File", "", "Muted", "Plan"]
FILE_COL = 1     # the single stretch column
STATUS_COL = 2   # 28px ✓/✗ glyph
OK_COLOR = QColor("#d2cefd")     # accent-300
ERR_COLOR = QColor("#eab7b7")    # error text


def _short_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %H:%M")
    except ValueError:
        return iso


def _compact_plan(plan: str) -> str:
    """'gigaam(v3) -> gigaam(v3) -> whisper(large-v3)' → 'GigaAM ×2 → Whisper'"""
    from itertools import groupby
    engines = []
    for part in plan.split("->"):
        part = part.strip().split("(")[0].strip().lower()
        if part:
            engines.append("GigaAM" if part == "gigaam" else "Whisper"
                           if part == "whisper" else part)
    parts = []
    for engine, run in groupby(engines):
        count = len(list(run))
        parts.append(engine if count == 1 else f"{engine} ×{count}")
    return " → ".join(parts)


class HistoryTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._records = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self.table = HoverRowTable(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [tr(c) if c else "" for c in COLUMNS])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(FILE_COL, QHeaderView.Stretch)
        header.setSectionResizeMode(STATUS_COL, QHeaderView.Fixed)
        self.table.setColumnWidth(STATUS_COL, 28)
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.itemDoubleClicked.connect(self._open_output)
        layout.addWidget(self.table, stretch=1)

        bottom = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setProperty("muted", True)
        bottom.addWidget(self.count_label)
        bottom.addStretch()
        self.folder_button = QPushButton(tr("Open results folder"))
        self.folder_button.clicked.connect(self._open_results_folder)
        bottom.addWidget(self.folder_button)
        clear = QPushButton(tr("Clear"))
        clear.setProperty("danger", True)
        clear.clicked.connect(self._clear)
        bottom.addWidget(clear)
        layout.addLayout(bottom)
        self.refresh()

    def refresh(self):
        self._records = history.load_history()
        self.table.setRowCount(len(self._records))
        for row, r in enumerate(self._records):
            status = r.get("status", "")
            error = r.get("error", "")
            status_item = QTableWidgetItem("✓" if status == "ok" else "✕")
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "ok":
                status_item.setForeground(OK_COLOR)
                status_item.setToolTip(tr("Done"))
            else:
                status_item.setForeground(ERR_COLOR)
                status_item.setToolTip(error or tr("Error"))
            time_item = QTableWidgetItem(_short_time(r.get("time", "")))
            time_item.setToolTip(r.get("time", ""))
            output = r.get("output", "")
            file_item = QTableWidgetItem(r.get("name", ""))
            if output:
                file_item.setToolTip(output)
            plan_item = QTableWidgetItem(_compact_plan(r.get("plan", "")))
            plan_item.setToolTip(r.get("plan", ""))
            values = [time_item, file_item, status_item,
                      QTableWidgetItem(str(r.get("muted", ""))), plan_item]
            for col, item in enumerate(values):
                self.table.setItem(row, col, item)
        self.count_label.setText(
            tr("{} record(s)").format(len(self._records)) if self._records
            else tr("Processed files will appear here."))

    # ---------------------------------------------------------- actions
    def _record_for_row(self, row: int):
        return self._records[row] if 0 <= row < len(self._records) else None

    def _open_output(self, item):
        r = self._record_for_row(item.row())
        if r and r.get("output") and Path(r["output"]).exists():
            os.startfile(r["output"])

    def _menu(self, pos):
        row = self.table.rowAt(pos.y())
        r = self._record_for_row(row)
        if r is None:
            return
        menu = QMenu(self)
        out = r.get("output", "")
        out_ok = bool(out and Path(out).exists())
        act_open = menu.addAction(tr("Open output"))
        act_open.setEnabled(out_ok)
        act_show = menu.addAction(tr("Show output in folder"))
        act_show.setEnabled(out_ok)
        act_copy = menu.addAction(tr("Copy error"))
        act_copy.setEnabled(bool(r.get("error")))
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is act_open:
            os.startfile(out)
        elif chosen is act_show:
            subprocess.Popen(["explorer", "/select,", str(Path(out))])
        elif chosen is act_copy:
            QGuiApplication.clipboard().setText(r.get("error", ""))

    def _open_results_folder(self):
        """Configured output folder; in beside-the-source mode, the
        selected (or most recent) record's folder."""
        settings = config.load_settings()
        if settings["output_mode"] == "folder" and settings["output_dir"]:
            folder = Path(settings["output_dir"])
            if folder.is_dir():
                os.startfile(str(folder))
                return
        row = self.table.currentRow()
        candidates = ([self._record_for_row(row)] if row >= 0 else []) \
            + self._records
        for r in candidates:
            out = (r or {}).get("output", "")
            if out and Path(out).parent.is_dir():
                if Path(out).exists():
                    subprocess.Popen(["explorer", "/select,", str(Path(out))])
                else:
                    os.startfile(str(Path(out).parent))
                return
        QMessageBox.information(self, "WordMute",
                                tr("Processed files will appear here."))

    def _clear(self):
        if QMessageBox.question(self, "WordMute",
                                tr("Clear the whole processing history?")) \
                == QMessageBox.StandardButton.Yes:
            history.clear_history()
            self.refresh()
