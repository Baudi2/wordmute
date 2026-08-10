"""Pick-up-and-drop reorder: slide math, drag lifecycle on real widget
lists (offscreen), the eventFilter mouse path driven by synthetic
events, owner integration for queue cards and pass chips. Animations
are collapsed to 0 ms so commits are synchronous."""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from wordmute_app.ui.animated_reorder import (
    AnimatedReorder,
    insert_index,
    slide_delta,
)


def _send_mouse(widget, type_, pos, button=Qt.LeftButton, buttons=None):
    if buttons is None:
        buttons = (Qt.NoButton if type_ == QEvent.MouseButtonRelease
                   else button)
    QApplication.sendEvent(widget, QMouseEvent(
        type_, QPointF(pos), QPointF(widget.mapToGlobal(pos)),
        button, buttons, Qt.NoModifier))


def _drag_by_events(lst, start, end):
    vp = lst.viewport()
    _send_mouse(vp, QEvent.MouseButtonPress, start)
    threshold = QApplication.startDragDistance() + 2
    _send_mouse(vp, QEvent.MouseMove, start + QPoint(0, threshold))
    _send_mouse(vp, QEvent.MouseMove, end)
    _send_mouse(vp, QEvent.MouseButtonRelease, end)


# ---------------------------------------------------------------- math
def test_slide_delta_matrix():
    # moving row 0 down to 2 in [0..3]: rows 1,2 slide up, 3 stays
    assert [slide_delta(r, 0, 2) for r in (1, 2, 3)] == [-1, -1, 0]
    # moving row 3 up to 1: rows 1,2 slide down, 0 stays
    assert [slide_delta(r, 3, 1) for r in (0, 1, 2)] == [0, 1, 1]
    # no move: nobody slides
    assert [slide_delta(r, 2, 2) for r in (0, 1, 3)] == [0, 0, 0]
    # adjacent swap down
    assert slide_delta(1, 0, 1) == -1
    # adjacent swap up
    assert slide_delta(1, 2, 1) == 1


def test_insert_index():
    centers = [10, 30, 50]
    assert insert_index(centers, 0) == 0
    assert insert_index(centers, 20) == 1
    assert insert_index(centers, 40) == 2
    assert insert_index(centers, 99) == 3
    assert insert_index([], 5) == 0


# ------------------------------------------------------------- fixtures
@pytest.fixture
def card_list(qapp):
    """A QueueList with three real cards, laid out offscreen."""
    from wordmute_app.ui.queue_card import CARD_HEIGHT, QueueCard, QueueList
    from PySide6.QtWidgets import QListWidgetItem

    lst = QueueList()
    lst.resize(400, 400)
    for name in ("a", "b", "c"):
        item = QListWidgetItem()
        lst.addItem(item)
        lst.setItemWidget(item, QueueCard(name, f"meta {name}"))
    lst.show()
    for _ in range(3):
        qapp.processEvents()
    lst.sync_sizes()
    qapp.processEvents()
    assert lst.visualItemRect(lst.item(0)).height() == CARD_HEIGHT
    yield lst
    lst.hide()


def _mid(lst, row) -> QPoint:
    return lst.visualItemRect(lst.item(row)).center()


# ------------------------------------------------------------ lifecycle
def test_drag_down_commits_single_move(qapp, card_list):
    moves = []
    ctrl = AnimatedReorder(card_list, lambda s, d: moves.append((s, d)))
    ctrl._land_ms = 0
    ctrl._slide_ms = 0

    ctrl._begin(0, _mid(card_list, 0))
    assert ctrl._src == 0
    # the source widget is hidden = the traveling gap
    assert not card_list.itemWidget(card_list.item(0)).isVisible()
    assert ctrl._lift is not None and ctrl._lift.isVisible()

    ctrl._drag_to(_mid(card_list, 2) + QPoint(0, 10))
    assert ctrl._dst == 2
    # rows 1 and 2 slid up one slot to open the gap at the bottom
    for row in (1, 2):
        base = card_list.visualItemRect(card_list.item(row)).topLeft()
        widget = card_list.itemWidget(card_list.item(row))
        assert widget.pos().y() == base.y() - ctrl._slot

    ctrl._settle(cancel=False)
    assert moves == [(0, 2)]
    assert ctrl._src == -1 and ctrl._lift is None


def test_drop_in_place_moves_nothing(qapp, card_list):
    moves = []
    ctrl = AnimatedReorder(card_list, lambda s, d: moves.append((s, d)))
    ctrl._land_ms = 0
    ctrl._slide_ms = 0

    ctrl._begin(1, _mid(card_list, 1))
    ctrl._drag_to(_mid(card_list, 1))
    assert ctrl._dst == 1
    ctrl._settle(cancel=False)
    assert moves == []
    widget = card_list.itemWidget(card_list.item(1))
    assert widget.isVisible()
    # back at its resting spot
    assert widget.pos() == \
        card_list.visualItemRect(card_list.item(1)).topLeft()


def test_escape_cancels_and_restores(qapp, card_list):
    moves = []
    ctrl = AnimatedReorder(card_list, lambda s, d: moves.append((s, d)))
    ctrl._land_ms = 0
    ctrl._slide_ms = 0

    ctrl._begin(0, _mid(card_list, 0))
    ctrl._drag_to(_mid(card_list, 2))
    ctrl._settle(cancel=True)
    assert moves == []
    for row in range(3):
        widget = card_list.itemWidget(card_list.item(row))
        assert widget.isVisible()
        assert widget.pos() == \
            card_list.visualItemRect(card_list.item(row)).topLeft()


def test_disabled_by_property(qapp, card_list):
    ctrl = AnimatedReorder(card_list, lambda s, d: None)
    card_list.setProperty("reorder_enabled", False)
    assert not ctrl._enabled()
    card_list.setProperty("reorder_enabled", True)
    assert ctrl._enabled()


# --------------------------------------------------- event-driven path
def test_event_driven_drag_commits(qapp, card_list):
    moves = []
    ctrl = AnimatedReorder(card_list, lambda s, d: moves.append((s, d)))
    ctrl._land_ms = 0
    ctrl._slide_ms = 0
    _drag_by_events(card_list, _mid(card_list, 0),
                    _mid(card_list, 2) + QPoint(0, 10))
    assert moves == [(0, 2)]


def test_event_driven_click_selects_without_move(qapp, card_list):
    moves = []
    AnimatedReorder(card_list, lambda s, d: moves.append((s, d)))
    vp = card_list.viewport()
    pos = _mid(card_list, 1)
    _send_mouse(vp, QEvent.MouseButtonPress, pos)
    _send_mouse(vp, QEvent.MouseMove, pos + QPoint(0, 2))  # sub-threshold
    _send_mouse(vp, QEvent.MouseButtonRelease, pos)
    assert moves == []
    assert card_list.item(1).isSelected()


def test_right_click_mid_drag_cancels(qapp, card_list):
    """Regression: a right-click used to open the context menu, eat the
    left release, and leave a stuck drag that mis-committed later."""
    moves = []
    ctrl = AnimatedReorder(card_list, lambda s, d: moves.append((s, d)))
    ctrl._land_ms = 0
    ctrl._slide_ms = 0
    vp = card_list.viewport()
    _send_mouse(vp, QEvent.MouseButtonPress, _mid(card_list, 0))
    _send_mouse(vp, QEvent.MouseMove, _mid(card_list, 2),
                buttons=Qt.LeftButton)
    assert ctrl._src == 0
    _send_mouse(vp, QEvent.MouseButtonPress, _mid(card_list, 2),
                button=Qt.RightButton,
                buttons=Qt.LeftButton | Qt.RightButton)
    # drag cancelled, nothing committed, widgets restored
    assert ctrl._src == -1
    assert moves == []
    assert card_list.itemWidget(card_list.item(0)).isVisible()
    # a later plain click must not commit a phantom move
    pos = _mid(card_list, 1)
    _send_mouse(vp, QEvent.MouseButtonPress, pos)
    _send_mouse(vp, QEvent.MouseButtonRelease, pos)
    assert moves == []


def test_gate_flipped_between_press_and_move(qapp, card_list):
    """Regression: a run starting (reorder_enabled=False) between the
    press and the move must not lift anything."""
    moves = []
    ctrl = AnimatedReorder(card_list, lambda s, d: moves.append((s, d)))
    vp = card_list.viewport()
    start = _mid(card_list, 0)
    _send_mouse(vp, QEvent.MouseButtonPress, start)
    card_list.setProperty("reorder_enabled", False)
    _send_mouse(vp, QEvent.MouseMove, start + QPoint(0, 40))
    assert ctrl._src == -1
    _send_mouse(vp, QEvent.MouseButtonRelease, start + QPoint(0, 40))
    assert moves == []
    card_list.setProperty("reorder_enabled", True)


def test_escape_key_event_cancels(qapp, card_list):
    moves = []
    ctrl = AnimatedReorder(card_list, lambda s, d: moves.append((s, d)))
    ctrl._land_ms = 0
    ctrl._slide_ms = 0
    vp = card_list.viewport()
    _send_mouse(vp, QEvent.MouseButtonPress, _mid(card_list, 0))
    _send_mouse(vp, QEvent.MouseMove, _mid(card_list, 2),
                buttons=Qt.LeftButton)
    assert ctrl._src == 0
    QApplication.sendEvent(card_list, QKeyEvent(
        QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert ctrl._src == -1
    assert moves == []


def test_abort_cancels_armed_and_lifted(qapp, card_list):
    moves = []
    ctrl = AnimatedReorder(card_list, lambda s, d: moves.append((s, d)))
    ctrl._slide_ms = 0
    ctrl._begin(0, _mid(card_list, 0))
    ctrl._drag_to(_mid(card_list, 2))
    ctrl.abort()
    assert ctrl._src == -1
    assert moves == []
    assert card_list.itemWidget(card_list.item(0)).isVisible()
    ctrl.abort()  # idle abort is a no-op
    assert moves == []


# ------------------------------------------------------------ owners
def test_queue_reorder_rebuilds_cards(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        f = tmp_path / name
        f.touch()
        w._add_files([f])
    w._apply_status(0, "done → a.clean.mp4", state="ok")

    w._move_queue_row(0, 2)
    assert [it.display_name for it in w._items()] == \
        ["b.mp4", "c.mp4", "a.mp4"]
    # cards rebuilt from roles: status traveled with its item
    assert w.status_text(2) == "done → a.clean.mp4"
    assert all(w._card(r) is not None for r in range(3))
    # run gating flips the controller's enable property
    w._set_running(True)
    assert w.queue.property("reorder_enabled") is False
    assert not w._queue_reorder._enabled()
    w._set_running(False)
    assert w._queue_reorder._enabled()


def test_queue_multi_select_moves_block(qapp, tmp_path, monkeypatch):
    """Parity with the old native drag: dragging a card that is part of
    a multi-selection moves the whole selected block and keeps it
    selected."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    for name in ("a.mp4", "b.mp4", "c.mp4", "d.mp4", "e.mp4"):
        f = tmp_path / name
        f.touch()
        w._add_files([f])
    for row in (1, 3):
        w.queue.item(row).setSelected(True)

    # drag row 1 (selected together with row 3) to the very end
    w._move_queue_row(1, 4)
    assert [it.display_name for it in w._items()] == \
        ["a.mp4", "c.mp4", "e.mp4", "b.mp4", "d.mp4"]
    # the moved block is still selected, current row on the grabbed one
    assert sorted(w.queue.row(i) for i in w.queue.selectedItems()) == [3, 4]
    assert w.queue.currentRow() == 3

    # bounds backstop: garbage indexes are ignored
    w._move_queue_row(99, 0)
    w._move_queue_row(0, 99)
    assert [it.display_name for it in w._items()] == \
        ["a.mp4", "c.mp4", "e.mp4", "b.mp4", "d.mp4"]


def test_chips_reorder_updates_plan(qapp):
    from wordmute_app.ui.plan_widget import PassPlanWidget

    plan = PassPlanWidget()
    plan.resize(400, 300)
    plan.show()
    qapp = __import__("PySide6.QtWidgets",
                      fromlist=["QApplication"]).QApplication.instance()
    for _ in range(3):
        qapp.processEvents()
    plan.set_engines(["whisper", "gigaam"])
    for _ in range(3):
        qapp.processEvents()

    ctrl = plan._reorder
    ctrl._land_ms = 0
    ctrl._slide_ms = 0
    lst = plan.chips
    ctrl._begin(0, lst.visualItemRect(lst.item(0)).center())
    assert ctrl._src == 0
    ctrl._drag_to(lst.visualItemRect(lst.item(1)).center()
                  + QPoint(0, 8))
    ctrl._settle(cancel=False)
    assert plan.engines() == ["gigaam", "whisper"]
    # chips rebuilt with fresh numbering widgets
    assert all(lst.itemWidget(lst.item(i)) is not None
               for i in range(lst.count()))
    plan.hide()
