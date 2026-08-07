"""Processing history viewer."""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core import history
from .i18n import tr

COLUMNS = ["Time", "File", "Status", "Muted", "Plan", "Output"]


class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("History…").rstrip("…"))
        self.resize(820, 480)
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        self.count_label = QLabel("")
        layout.addWidget(self.count_label)

        buttons = QHBoxLayout()
        clear = QPushButton(tr("Clear"))
        clear.clicked.connect(self._clear)
        buttons.addWidget(clear)
        buttons.addStretch()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self):
        records = history.load_history()
        self.table.setRowCount(len(records))
        for row, r in enumerate(records):
            status = r.get("status", "")
            if status == "error":
                status = f"error: {r.get('error', '')}"
            values = [r.get("time", ""), r.get("name", ""), status,
                      str(r.get("muted", "")), r.get("plan", ""),
                      r.get("output", "")]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.count_label.setText(f"{len(records)} record(s)")

    def _clear(self):
        if QMessageBox.question(self, "WordMute",
                                "Clear the whole processing history?") \
                == QMessageBox.StandardButton.Yes:
            history.clear_history()
            self.refresh()
