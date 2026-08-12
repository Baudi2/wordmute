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

from ..core import cleanup, config, history
from .file_delete import confirm_and_recycle
from .hover_table import HoverRowTable
from .i18n import tr

COLUMNS = ["Time", "File", "", "Muted", "Plan", ""]
FILE_COL = 1     # the single stretch column
STATUS_COL = 2   # 28px ✓/✗ glyph
FILES_COL = 5    # 28px ●/◐/○ files-on-disk glyph
OK_COLOR = QColor("#d2cefd")     # accent-300
ERR_COLOR = QColor("#eab7b7")    # error text
DIM_COLOR = QColor("#9096a0")    # muted text


def _short_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %H:%M")
    except ValueError:
        return iso


def _files_glyph(record: dict):
    """(glyph, tooltip_key) for the files-on-disk column: ● all tracked
    files present, ◐ some deleted, ○ all deleted. Only local paths
    count — old records stored the URL as source."""
    tracked = []
    src = record.get("source", "")
    if src and Path(src).is_absolute():
        tracked.append(("source", Path(src).exists()))
    out = record.get("output", "")
    if out:
        tracked.append(("output", Path(out).exists()))
    if not tracked:
        return "", ""
    present = [name for name, exists in tracked if exists]
    if len(present) == len(tracked):
        return "●", "Files on disk"
    if not present:
        return "○", "Files deleted"
    return "◐", ("Source deleted" if present == ["output"]
                 else "Output deleted")


def _fmt_stages(stages: dict) -> str:
    """«скачивание 2 мин 10 с · Whisper 8 мин 3 с · заглушение 45 с ·
    итого 11 мин» — from the worker's stage_seconds record."""
    from .main_window import fmt_hms  # lazy: main_window imports us
    parts = []
    if stages.get("download"):
        parts.append(f"{tr('downloading')} {fmt_hms(stages['download'])}")
    for p in stages.get("passes", []):
        label = "GigaAM" if p.get("engine") == "gigaam" else "Whisper"
        if p.get("cached"):
            parts.append(f"{label}: {tr('from cache')}")
        else:
            parts.append(f"{label} {fmt_hms(p.get('seconds', 0))}")
    if stages.get("mute"):
        parts.append(f"{tr('muting')} {fmt_hms(stages['mute'])}")
    if stages.get("total"):
        parts.append(f"{tr('total')} {fmt_hms(stages['total'])}")
    return " · ".join(parts)


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
        header.setSectionResizeMode(FILES_COL, QHeaderView.Fixed)
        self.table.setColumnWidth(FILES_COL, 28)
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
        self.traffic_label = QLabel("")
        self.traffic_label.setProperty("muted", True)
        self.traffic_label.setToolTip(
            tr("Videos downloaded by link this calendar month — handy "
               "for metered/VPN connections. Component and model "
               "downloads are not included."))
        bottom.addWidget(self.traffic_label)
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
            name = r.get("name", "")
            if name.startswith(("http://", "https://")):
                # older records of batch-added links stored the URL;
                # the recorded local file name is the real title
                src = r.get("source", "")
                if src and Path(src).is_absolute():
                    name = Path(src).stem
            file_item = QTableWidgetItem(name)
            tip_lines = [output] if output else []
            stage_text = _fmt_stages(r.get("stage_seconds") or {})
            if stage_text:
                tip_lines.append(stage_text)
            if tip_lines:
                file_item.setToolTip("\n".join(tip_lines))
            plan_item = QTableWidgetItem(_compact_plan(r.get("plan", "")))
            plan_item.setToolTip(r.get("plan", ""))
            glyph, tip = _files_glyph(r)
            files_item = QTableWidgetItem(glyph)
            files_item.setTextAlignment(Qt.AlignCenter)
            files_item.setForeground(OK_COLOR if glyph == "●"
                                     else DIM_COLOR)
            if tip:
                files_item.setToolTip(tr(tip))
            values = [time_item, file_item, status_item,
                      QTableWidgetItem(str(r.get("muted", ""))), plan_item,
                      files_item]
            for col, item in enumerate(values):
                self.table.setItem(row, col, item)
        self.count_label.setText(
            tr("{} record(s)").format(len(self._records)) if self._records
            else tr("Processed files will appear here."))
        month = history.month_traffic()
        if month:
            from ..core.models import fmt_size
            self.traffic_label.setText(
                "· " + tr("downloaded this month: {}")
                .format(fmt_size(month)))
        else:
            self.traffic_label.setText("")

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
        menu.addSeparator()
        act_del_src = menu.addAction(tr("Delete source video and JSONs"))
        act_del_src.setEnabled(bool(self._files_for_row(row, False)))
        act_del_all = menu.addAction(
            tr("Delete all files (source, clean, JSONs)"))
        act_del_all.setEnabled(bool(self._files_for_row(row, True)))
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is act_open:
            os.startfile(out)
        elif chosen is act_show:
            subprocess.Popen(["explorer", "/select,", str(Path(out))])
        elif chosen is act_copy:
            QGuiApplication.clipboard().setText(r.get("error", ""))
        elif chosen is act_del_src:
            self._delete_row_files(row, include_output=False)
        elif chosen is act_del_all:
            self._delete_row_files(row, include_output=True)

    def _files_for_row(self, row: int, include_output: bool) -> list:
        r = self._record_for_row(row)
        if r is None:
            return []
        out = r.get("output", "") or None
        source = cleanup.resolve_source(output=out,
                                        fallback=r.get("source") or None)
        return cleanup.related_files(source=source, output=out,
                                     include_output=include_output)

    def _delete_row_files(self, row: int, include_output: bool):
        if confirm_and_recycle(self, self._files_for_row(row,
                                                         include_output)):
            self.refresh()

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
