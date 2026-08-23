"""Pick-up-and-drop reordering for vertical QListWidget card/chip lists.

Replaces the native QDrag InternalMove (translucent ghost + insertion
line) with the modern pattern: the pressed item lifts out of the list
as a floating snapshot under the cursor, the remaining items slide
apart with a short animation so a single gap travels to where the item
would land, and releasing commits ONE model move via the owner's
callback.

Why not native: the view owns item geometry during a QDrag, and
setItemWidget widgets are destroyed by drag-moves (see CLAUDE.md), so
items cannot animate mid-drag. This controller instead drives the drag
from raw mouse events on the viewport and never touches the model
until drop; in between it only repositions the existing item WIDGETS.
All geometry is re-derived from visualItemRect() on every update, so
any relayout the view performs (scrolling included) is absorbed
instead of fought."""

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QGraphicsDropShadowEffect,
    QLabel,
)

SLIDE_MS = 140          # items parting / closing ranks
LAND_MS = 120           # lifted item settling into the gap
LIFT_SCALE = 1.03       # "picked up" = slightly enlarged + shadow
EDGE_MARGIN = 28        # autoscroll trigger zone at the viewport edges
EDGE_STEP = 12          # px per autoscroll tick


def slide_delta(row: int, src: int, dst: int) -> int:
    """Slot shift for a non-source row when the source leaves `src` and
    lands at `dst` (take-out/re-insert semantics): -1 = one slot up,
    +1 = one slot down, 0 = stays."""
    if src < dst and src < row <= dst:
        return -1
    if dst < src and dst <= row < src:
        return 1
    return 0


def insert_index(centers, y) -> int:
    """Landing position among the remaining items = how many of their
    resting slot centers lie above the cursor."""
    return sum(1 for c in centers if c < y)


class AnimatedReorder(QObject):
    """Attach to a vertical QListWidget whose rows carry item widgets.
    on_reorder(src, dst) is called once per completed drag; the owner
    performs the model move and rebuilds its widgets. Disable by
    setting a false "reorder_enabled" property on the list.
    lift_radius = the widget's QSS border-radius, so the floating
    snapshot gets truly transparent rounded corners (grab() captures
    the square corner pixels as opaque)."""

    def __init__(self, view, on_reorder, lift_radius: int = 0):
        super().__init__(view)
        self._view = view
        self._on_reorder = on_reorder
        self._lift_radius = lift_radius
        self._src = -1
        self._dst = -1
        self._lift = None            # floating snapshot QLabel
        self._grab = QPoint()        # press offset inside the card
        self._pad = QPoint()         # extra size from LIFT_SCALE, halved
        self._press_pos = None
        self._press_row = -1
        self._last_pos = None
        self._slot = 0               # slot height incl. inter-item gap
        self._anims = {}             # row -> (animation, target QPoint)
        self._landing = False
        self._land_ms = LAND_MS      # tests set 0 to commit synchronously
        self._slide_ms = SLIDE_MS
        self._edge_timer = QTimer(self)
        self._edge_timer.setInterval(30)
        self._edge_timer.timeout.connect(self._edge_scroll)
        # default ScrollPerItem would make the scrollbar (and the edge
        # autoscroll step) move whole ROWS per unit
        view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        view.viewport().installEventFilter(self)
        view.installEventFilter(self)
        view.verticalScrollBar().valueChanged.connect(self._on_scrolled)

    # ------------------------------------------------------------ events
    def eventFilter(self, obj, event):
        # the C++ side can outlive the Python attributes during teardown
        if getattr(self, "_view", None) is None:
            return False
        if obj is self._view:
            if (event.type() == QEvent.KeyPress
                    and event.key() == Qt.Key_Escape
                    and self._src >= 0 and not self._landing):
                self._settle(cancel=True)
                return True
            return False
        t = event.type()
        if t == QEvent.ContextMenu and (self._src >= 0 or self._landing):
            return True     # no context menu over a live drag
        if t == QEvent.MouseButtonPress:
            if event.button() != Qt.LeftButton:
                if self._src >= 0 and not self._landing:
                    self._settle(cancel=True)   # right-click = cancel
                    return True
                if self._landing:
                    return True
                # a popup may eat the matching release — disarm now
                self._disarm()
                return False
            if self._landing or self._src >= 0:
                return True
            if self._enabled():
                pos = event.position().toPoint()
                self._press_row = self._row_at(pos)
                self._press_pos = pos if self._press_row >= 0 else None
            return False    # the view still handles selection/clicks
        if t == QEvent.MouseMove:
            if self._landing:
                return True     # never retarget a drop in flight
            if self._src >= 0:
                if not event.buttons() & Qt.LeftButton:
                    # the release was eaten (popup, focus loss): bail
                    self._settle(cancel=True)
                    return True
                self._drag_to(event.position().toPoint())
                return True
            if self._press_pos is not None:
                if not event.buttons() & Qt.LeftButton:
                    self._disarm()      # stale arm: keep hover working
                    return False
                if not self._enabled():
                    self._disarm()      # gate flipped since the press
                    return False
                if (event.position().toPoint() - self._press_pos)\
                        .manhattanLength() \
                        >= QApplication.startDragDistance():
                    self._begin(self._press_row,
                                event.position().toPoint())
                    return self._src >= 0
                return True     # armed: block the view's drag-select
            return False
        if t == QEvent.MouseButtonRelease:
            if event.button() != Qt.LeftButton:
                return self._src >= 0 or self._landing
            self._disarm()
            if self._landing:
                return True
            if self._src >= 0:
                self._settle(cancel=False)
                return True
            return False
        return False

    def _disarm(self):
        self._press_pos = None
        self._press_row = -1

    def abort(self):
        """Synchronously finish any armed or in-flight drag — called
        before anything that remaps queue rows (e.g. a run starting)."""
        self._disarm()
        if self._src < 0:
            return
        if self._landing:
            anim = getattr(self, "_land_anim", None)
            if anim is not None:
                # stop() emits finished ONLY when the animation is
                # already at its end — mid-flight it does not, which
                # left the lift floating and the viewport's mouse grab
                # held: the whole window went mouse-dead
                anim.stop()
            if self._landing:            # finished did not fire
                self._commit(self._land_cancel)
            return
        land, self._land_ms = self._land_ms, 0
        try:
            self._settle(cancel=True)
        finally:
            self._land_ms = land

    def _enabled(self) -> bool:
        prop = self._view.property("reorder_enabled")
        return (prop is None or bool(prop)) and self._view.count() > 1

    def _row_at(self, pos) -> int:
        item = self._view.itemAt(pos)
        if item is not None and self._view.itemWidget(item) is not None:
            return self._view.row(item)
        return -1

    # ------------------------------------------------------------ drag
    def _begin(self, row: int, pos):
        self._disarm()
        widget = (self._view.itemWidget(self._view.item(row))
                  if row >= 0 else None)
        if widget is None or not self._enabled():
            return
        self._src = row
        self._dst = row              # gap starts where the item was
        rect = self._view.visualItemRect(self._view.item(row))
        self._slot = rect.height() + self._gap()
        self._grab = pos - rect.topLeft()

        snapshot = widget.grab()
        scaled = snapshot.scaled(
            round(snapshot.width() * LIFT_SCALE),
            round(snapshot.height() * LIFT_SCALE),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        scaled = self._round_corners(scaled)
        self._pad = QPoint((scaled.width() - snapshot.width()) // 2,
                           (scaled.height() - snapshot.height()) // 2)
        # parented to the WINDOW, not the viewport: a full-width card
        # scaled up (and its shadow) must overhang the list edges
        # instead of being clipped by them
        self._lift = QLabel(self._view.window())
        self._lift.setPixmap(scaled)
        self._lift.resize(scaled.size())
        shadow = QGraphicsDropShadowEffect(self._lift)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 110))
        self._lift.setGraphicsEffect(shadow)
        self._lift.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._lift.show()
        self._lift.raise_()

        widget.hide()                # its slot becomes the traveling gap
        # hiding the pressed widget clears Qt's implicit mouse grab, so
        # a release outside the viewport would be LOST and the drag
        # would hang mid-air; an explicit grab routes every mouse event
        # here until _commit releases it
        self._view.viewport().grabMouse()
        self._drag_to(pos)

    def _round_corners(self, pixmap: QPixmap) -> QPixmap:
        """grab() fills the QSS-rounded corners with opaque background;
        re-clip with real alpha so the lifted snapshot floats clean."""
        if self._lift_radius <= 0:
            return pixmap
        radius = self._lift_radius * LIFT_SCALE
        out = QPixmap(pixmap.size())
        out.setDevicePixelRatio(pixmap.devicePixelRatio())
        out.fill(Qt.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0,
                            pixmap.width() / pixmap.devicePixelRatio(),
                            pixmap.height() / pixmap.devicePixelRatio(),
                            radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return out

    def _lift_move(self, viewport_pos):
        """Position the window-parented lift from viewport coords."""
        self._lift.move(self._view.viewport().mapTo(
            self._view.window(), viewport_pos))

    def _gap(self) -> int:
        if self._view.count() >= 2:
            a = self._view.visualItemRect(self._view.item(0))
            b = self._view.visualItemRect(self._view.item(1))
            # QRect.bottom() is top+height-1, hence the -1
            return max(0, b.top() - a.bottom() - 1)
        return 2 * self._view.spacing()

    def _drag_to(self, pos):
        self._last_pos = pos
        rect = self._view.visualItemRect(self._view.item(self._src))
        self._lift_move(QPoint(rect.left() - self._pad.x(),
                               pos.y() - self._grab.y() - self._pad.y()))
        centers = [
            self._view.visualItemRect(self._view.item(r)).center().y()
            for r in range(self._view.count()) if r != self._src]
        self._dst = insert_index(centers, pos.y())
        self._animate_slides(self._slide_ms)

        near_top = pos.y() < EDGE_MARGIN
        near_bottom = pos.y() > self._view.viewport().height() - EDGE_MARGIN
        if near_top or near_bottom:
            self._edge_dir = -1 if near_top else 1
            if not self._edge_timer.isActive():
                self._edge_timer.start()
        else:
            self._edge_timer.stop()

    def _animate_slides(self, duration: int):
        for row in range(self._view.count()):
            if row == self._src:
                continue
            widget = self._view.itemWidget(self._view.item(row))
            if widget is None:
                continue
            base = self._view.visualItemRect(self._view.item(row)).topLeft()
            delta = slide_delta(row, self._src, self._dst)
            target = base + QPoint(0, delta * self._slot)
            anim, prev_target = self._anims.get(row, (None, None))
            if prev_target == target:
                continue
            if anim is not None:
                anim.stop()
                anim.deleteLater()
            if duration <= 0:
                widget.move(target)
                self._anims[row] = (None, target)
                continue
            anim = QPropertyAnimation(widget, b"pos", self)
            anim.setDuration(duration)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.setStartValue(widget.pos())
            anim.setEndValue(target)
            anim.start()
            self._anims[row] = (anim, target)

    def _edge_scroll(self):
        bar = self._view.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + self._edge_dir * EDGE_STEP)
        if bar.value() == before:
            self._edge_timer.stop()

    def _on_scrolled(self, *_):
        # any scroll relayouts the widgets to their resting spots;
        # re-derive everything from the fresh geometry
        if self._src >= 0 and not self._landing \
                and self._last_pos is not None:
            self._drag_to(self._last_pos)

    # ------------------------------------------------------------ drop
    def _settle(self, cancel: bool):
        """Fly the lifted snapshot into the gap, then commit."""
        if self._landing:
            return          # a drop is already in flight
        self._edge_timer.stop()
        if cancel:
            self._dst = self._src
        self._animate_slides(0 if self._land_ms <= 0 else self._slide_ms)
        # visualItemRect is model-derived (our widget moves never touch
        # it), so row 0's resting top anchors the uniform slot grid
        grid_top = self._view.visualItemRect(self._view.item(0)).top()
        final_y = grid_top + self._dst * self._slot
        rect = self._view.visualItemRect(self._view.item(self._src))
        end = self._view.viewport().mapTo(
            self._view.window(),
            QPoint(rect.left() - self._pad.x(), final_y - self._pad.y()))
        self._landing = True
        self._land_cancel = cancel       # abort() may have to commit
        if self._land_ms <= 0:
            self._commit(cancel)
            return
        anim = QPropertyAnimation(self._lift, b"pos", self)
        anim.setDuration(self._land_ms)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(self._lift.pos())
        anim.setEndValue(end)
        anim.finished.connect(lambda: self._commit(cancel))
        anim.start()
        self._land_anim = anim       # keep alive until finished

    def _commit(self, cancel: bool):
        if self._src < 0:
            return                       # already committed
        src, dst = self._src, self._dst
        self._edge_timer.stop()
        if self._view.viewport().mouseGrabber() is self._view.viewport():
            self._view.viewport().releaseMouse()
        for anim, _target in self._anims.values():
            if anim is not None:
                anim.stop()
                anim.deleteLater()
        self._anims.clear()
        land = getattr(self, "_land_anim", None)
        if land is not None:
            land.deleteLater()
            self._land_anim = None
        widget = self._view.itemWidget(self._view.item(src))
        if self._lift is not None:
            self._lift.deleteLater()
            self._lift = None
        if widget is not None:
            widget.show()
        self._src = -1
        self._dst = -1
        self._landing = False
        self._last_pos = None
        if not cancel and dst != src:
            self._on_reorder(src, dst)
        else:
            # snap everything back to its resting geometry
            for row in range(self._view.count()):
                w = self._view.itemWidget(self._view.item(row))
                if w is not None:
                    w.move(self._view.visualItemRect(
                        self._view.item(row)).topLeft())
