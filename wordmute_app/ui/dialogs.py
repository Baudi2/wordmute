"""Themed menus and confirmations (design 0.6.1, section 1a).

Two things the base stylesheet could never reach:

* QMenu — the sheet styled the menu, but the platform still drew a rim
  and a native drop shadow around our rounded corners, and the check
  glyph / submenu arrow stayed native. Frameless + translucent fixes
  the frame; the sheet owns the sub-controls.
* QMessageBox — its icon is a platform pixmap and its buttons take
  their text from Qt's own catalog, which is why a Russian window
  showed English Yes/No. It is replaced by ConfirmDialog: same shell
  as the rest of the app, and the primary button names the action
  («В Корзину», «Удалить») instead of answering a question.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .theme import ui_icon

# result of ConfirmDialog.exec() beyond accept/reject
ALT = 2

_SEVERITY_COLOR = {"danger": "#cd8484", "warn": "#cdb380", "info": "#9397ab"}


def repolish(widget) -> None:
    """Re-evaluate the stylesheet after setProperty — every property the
    sheet keys on (danger, state, severity, dragOver, accepts) needs it."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def themed_menu(parent, object_name: str) -> QMenu:
    """A QMenu without the platform frame around our rounded corners."""
    menu = QMenu(parent)
    menu.setObjectName(object_name)
    menu.setWindowFlags(menu.windowFlags()
                        | Qt.FramelessWindowHint
                        | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


def mark_danger(action) -> None:
    """Destructive menu entry.

    The design asked for red text via QMenu#card_menu::item[danger] —
    Qt cannot do that: QSS sub-control selectors read the MENU widget's
    properties, never the QAction's, so a per-item color is impossible
    without replacing the row with a QWidgetAction (and losing native
    keyboard handling). A red-tinted trash icon carries the same signal
    at no structural cost; the property is still set so the sheet's rule
    applies if a future Qt honors it."""
    action.setProperty("danger", True)
    action.setIcon(ui_icon("trash", 14, _SEVERITY_COLOR["danger"]))


class ConfirmDialog(QDialog):
    """Fixed 460 wide, height from content. The primary button carries
    the verb; on destructive dialogs Cancel is the default button, so a
    stray Enter never deletes anything."""

    def __init__(self, parent=None, *, title: str, body: str = "",
                 files=(), ok_text: str, alt_text: str = None,
                 cancel_text: str = None, severity: str = "danger"):
        super().__init__(parent)
        self.setObjectName("wm_confirm")
        self.setWindowTitle("WordMute")
        self.setModal(True)
        self.setFixedWidth(460)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QHBoxLayout()
        content.setContentsMargins(20, 20, 20, 16)
        content.setSpacing(14)
        icon = QLabel()
        icon.setObjectName("wm_confirm_icon")
        icon.setProperty("severity", severity)
        icon.setPixmap(ui_icon("warning", 16,
                               _SEVERITY_COLOR.get(severity, "#9397ab"))
                       .pixmap(16, 16))
        content.addWidget(icon, alignment=Qt.AlignTop)

        column = QVBoxLayout()
        column.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("wm_confirm_title")
        title_label.setWordWrap(True)
        column.addWidget(title_label)
        if body:
            body_label = QLabel(body)
            body_label.setObjectName("wm_confirm_body")
            body_label.setWordWrap(True)
            column.addWidget(body_label)
        if files:
            listing = QPlainTextEdit()
            listing.setObjectName("wm_confirm_files")
            listing.setReadOnly(True)
            # one row per file, middle-elided: real names (downloaded
            # episodes) are long enough to wrap to three lines each,
            # which turned the box into a wall of half-cut text
            listing.setLineWrapMode(QPlainTextEdit.NoWrap)
            listing.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            listing.setToolTip("\n".join(str(f) for f in files))
            self._files_widget = listing
            self._file_names = [str(f) for f in files]
            metrics = QFontMetrics(listing.font())
            rows = min(len(files), 6)
            # frame + padding (9px top/bottom from the sheet) + rows
            listing.setFixedHeight(2 * (9 + listing.frameWidth())
                                   + rows * metrics.lineSpacing())
            if len(files) <= 6:
                listing.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            column.addWidget(listing)
            self._elide_files()
        content.addLayout(column, stretch=1)
        root.addLayout(content)

        footer = QWidget()
        footer.setObjectName("wm_confirm_footer")
        footer.setFixedHeight(58)
        row = QHBoxLayout(footer)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(9)
        row.addStretch()
        cancel = QPushButton(cancel_text or tr("Cancel"))
        cancel.setObjectName("btn_confirm_cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        if alt_text:
            alt = QPushButton(alt_text)
            alt.setObjectName("btn_confirm_alt")
            alt.clicked.connect(lambda: self.done(ALT))
            row.addWidget(alt)
        ok = QPushButton(ok_text)
        ok.setObjectName("btn_confirm_ok")
        ok.setProperty("primary", True)
        if severity == "danger":
            ok.setProperty("danger", True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        root.addWidget(footer)

        # destructive dialogs default to Cancel; informational ones to OK
        (cancel if severity == "danger" else ok).setDefault(True)
        self.ok_button, self.cancel_button = ok, cancel

    def _elide_files(self) -> None:
        listing = getattr(self, "_files_widget", None)
        if listing is None:
            return
        # measure with the font the sheet actually renders (mono 11px),
        # which the widget only carries once polished — the same trap
        # that clipped the toasts
        listing.ensurePolished()
        metrics = QFontMetrics(listing.font())
        width = listing.viewport().width() or (listing.width() - 24)
        # the document keeps a 4px margin on each side
        width = max(width - 2 * int(listing.document().documentMargin()), 40)
        listing.setPlainText("\n".join(
            metrics.elidedText(name, Qt.ElideMiddle, width)
            for name in self._file_names))

    def showEvent(self, event):
        super().showEvent(event)
        self._elide_files()      # geometry and style are final now

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_files()


def confirm(parent, *, title: str, body: str = "", files=(),
            ok_text: str, severity: str = "danger") -> bool:
    return ConfirmDialog(parent, title=title, body=body, files=files,
                         ok_text=ok_text,
                         severity=severity).exec() == QDialog.Accepted


def inform(parent, *, title: str, body: str = "", files=()) -> None:
    """One-button notice — the themed stand-in for QMessageBox.information."""
    dialog = ConfirmDialog(parent, title=title, body=body, files=files,
                           ok_text=tr("Got it"), severity="info")
    dialog.cancel_button.hide()
    dialog.exec()
