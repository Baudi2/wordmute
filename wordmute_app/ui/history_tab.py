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

from ..core import history
from .hover_table import HoverRowTable
from .i18n import tr

COLUMNS = ["Time", "File", "Status", "Muted", "Plan", "Output"]
OK_COLOR = QColor("#d2cefd")     # accent-300
ERR_COLOR = QColor("#eab7b7")    # error text


def _short_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %H:%M")
    except ValueError:
        return iso


class HistoryTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._records = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self.table = HoverRowTable(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
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
            status_item = QTableWidgetItem(
                f"error: {error}" if status == "error" else status)
            if status == "ok":
                status_item.setForeground(OK_COLOR)
            elif status == "error":
                status_item.setForeground(ERR_COLOR)
                status_item.setToolTip(error)
            time_item = QTableWidgetItem(_short_time(r.get("time", "")))
            time_item.setToolTip(r.get("time", ""))
            output = r.get("output", "")
            output_item = QTableWidgetItem(Path(output).name if output
                                           else "")
            output_item.setToolTip(output)
            values = [time_item, QTableWidgetItem(r.get("name", "")),
                      status_item, QTableWidgetItem(str(r.get("muted", ""))),
                      QTableWidgetItem(r.get("plan", "")), output_item]
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

    def _clear(self):
        if QMessageBox.question(self, "WordMute",
                                tr("Clear the whole processing history?")) \
                == QMessageBox.StandardButton.Yes:
            history.clear_history()
            self.refresh()
