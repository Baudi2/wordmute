"""One queue card: thumbnail, title, meta line, status + thin progress,
per-state action buttons (per design v3)."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

from .i18n import tr

THUMB_W, THUMB_H = 96, 54
CARD_HEIGHT = 80


class QueueList(QListWidget):
    """Card container: item size hints track the viewport width so each
    card spans the full row (item widgets are laid out inside the
    item's rect, not the list's). Reordering is pick-up-and-drop via
    AnimatedReorder (attached by the owner) — no native QDrag."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSpacing(4)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sync_sizes()

    def sync_sizes(self):
        width = self.viewport().width() - 2 * self.spacing()
        for i in range(self.count()):
            self.item(i).setSizeHint(QSize(width, CARD_HEIGHT))


def rounded_pixmap(source: QPixmap, w: int = THUMB_W, h: int = THUMB_H,
                   radius: int = 6) -> QPixmap:
    """QSS border-radius can't clip a pixmap — round it while drawing."""
    scaled = source.scaled(w, h, Qt.KeepAspectRatioByExpanding,
                           Qt.SmoothTransformation)
    out = QPixmap(w, h)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(-(scaled.width() - w) // 2,
                       -(scaled.height() - h) // 2, scaled)
    painter.end()
    return out


class QueueCard(QFrame):
    review_clicked = Signal()
    open_clicked = Signal()
    retry_clicked = Signal()
    menu_clicked = Signal(object)  # the ⋮ button, for menu positioning

    def __init__(self, title: str, meta: str, glyph: str = "▶",
                 parent=None):
        super().__init__(parent)
        self.setProperty("videoCard", True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        self.thumb = QLabel(glyph)
        self.thumb.setObjectName("card_thumb")
        self.thumb.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.thumb)
        self._pulse = None

        middle = QVBoxLayout()
        middle.setSpacing(2)
        # Ignored horizontal policy: long titles/paths/statuses clip
        # (full text in tooltip) instead of squeezing the action buttons
        self.title_label = QLabel(title)
        self.title_label.setObjectName("card_title")
        self.title_label.setToolTip(title)
        self.title_label.setSizePolicy(QSizePolicy.Ignored,
                                       QSizePolicy.Preferred)
        middle.addWidget(self.title_label)
        self.meta_label = QLabel(meta)
        self.meta_label.setObjectName("card_meta")
        self.meta_label.setToolTip(meta)
        self.meta_label.setSizePolicy(QSizePolicy.Ignored,
                                      QSizePolicy.Preferred)
        middle.addWidget(self.meta_label)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.status_label = QLabel(tr("queued"))
        self.status_label.setObjectName("card_status")
        self.status_label.setSizePolicy(QSizePolicy.Ignored,
                                        QSizePolicy.Preferred)
        status_row.addWidget(self.status_label, stretch=1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(140)
        self.progress.setVisible(False)
        status_row.addWidget(self.progress)
        middle.addLayout(status_row)
        layout.addLayout(middle, stretch=1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.review_button = QPushButton(tr("Review"))
        self.review_button.setProperty("primary", True)
        self.review_button.clicked.connect(self.review_clicked)
        self.open_button = QPushButton(tr("Open"))
        self.open_button.clicked.connect(self.open_clicked)
        self.retry_button = QPushButton(tr("Retry"))
        self.retry_button.clicked.connect(self.retry_clicked)
        self.more_button = QToolButton()
        self.more_button.setText("⋮")
        self.more_button.clicked.connect(
            lambda: self.menu_clicked.emit(self.more_button))
        for b in (self.review_button, self.open_button, self.retry_button):
            b.setVisible(False)
            actions.addWidget(b)
        actions.addWidget(self.more_button)
        layout.addLayout(actions)

    # ---------------------------------------------------------- state
    def set_selected(self, on: bool):
        if self.property("selected") == (on or None):
            return
        self.setProperty("selected", True if on else None)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_loading(self, on: bool):
        """Skeleton shimmer: pulse the thumbnail while the duration/
        thumbnail probe runs in the background (bulk adds)."""
        if on and self._pulse is None:
            from PySide6.QtCore import QPropertyAnimation
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            effect = QGraphicsOpacityEffect(self.thumb)
            self.thumb.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(900)
            anim.setStartValue(0.35)
            anim.setKeyValueAt(0.5, 0.9)
            anim.setEndValue(0.35)
            anim.setLoopCount(-1)
            anim.start()
            self._pulse = anim
        elif not on and self._pulse is not None:
            self._pulse.stop()
            self._pulse.deleteLater()
            self._pulse = None
            self.thumb.setGraphicsEffect(None)

    def set_thumb(self, path):
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self.set_loading(False)
            self.thumb.setPixmap(rounded_pixmap(pixmap))
            self.thumb.setText("")

    def set_title(self, title: str):
        self.title_label.setText(title)
        self.title_label.setToolTip(title)

    def set_meta(self, meta: str):
        self.meta_label.setText(meta)
        self.meta_label.setToolTip(meta)

    def status_text(self) -> str:
        return self.status_label.text()

    def set_status(self, text: str, state=None, progress=None):
        self.status_label.setText(text)
        if self.status_label.property("state") != state:
            self.status_label.setProperty("state", state)
            style = self.status_label.style()
            style.unpolish(self.status_label)
            style.polish(self.status_label)
        if progress is None:
            self.progress.setVisible(False)
        else:
            self.progress.setVisible(True)
            self.progress.setValue(int(min(max(progress, 0.0), 1.0) * 100))

    def set_actions(self, review: bool = False, open_: bool = False,
                    retry: bool = False):
        self.review_button.setVisible(review)
        self.open_button.setVisible(open_)
        self.retry_button.setVisible(retry)
