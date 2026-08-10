"""Review dialog offscreen: table population, checkbox editing,
re-render flow (with playback and apply_review stubbed)."""

import pytest
from PySide6.QtCore import Qt

from wordmute_app.core import review


class DummyPlayer:
    def __init__(self):
        self.played = []

    def play(self, media, s, e):
        self.played.append((media, s, e))

    def stop(self):
        pass

    def dispose(self):
        pass


@pytest.fixture
def review_file(tmp_path):
    source = tmp_path / "v.mp4"
    source.write_bytes(b"original")
    output = tmp_path / "v.clean.mp4"
    output.write_bytes(b"muted-output")
    intervals = [
        {"s": 1.0, "e": 1.5, "text": "бог", "pass": 1,
         "engine": "whisper", "muted": True},
        {"s": 9.0, "e": 9.4, "text": "обожаю", "pass": 2,
         "engine": "gigaam", "muted": True},
    ]
    return review.save_review(source, output, 100, intervals)


@pytest.fixture
def dialog(qapp, review_file, monkeypatch):
    from wordmute_app.ui import review_dialog
    monkeypatch.setattr(review_dialog, "SnippetPlayer", DummyPlayer)
    return review_dialog.ReviewDialog(review_file)


def test_table_populated(dialog):
    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 5).text() == "бог"
    assert dialog.table.item(1, 3).text() == "2"
    assert dialog.table.item(1, 4).text() == "gigaam"
    assert dialog.table.item(0, 0).checkState() == Qt.Checked
    assert "2 interval(s)" in dialog.counts_label.text()


def test_uncheck_marks_unmuted_and_dirty(dialog):
    dialog.table.item(0, 0).setCheckState(Qt.Unchecked)
    assert dialog._data["intervals"][0]["muted"] is False
    assert dialog._dirty is True
    assert "1 will be un-muted" in dialog.counts_label.text()


def test_hover_does_not_mark_dirty(dialog):
    # regression: row-hover sets cell backgrounds, which fires
    # itemChanged; that must never count as a user edit
    dialog.table._set_hover(0)
    dialog.table._set_hover(1)
    dialog.table._set_hover(-1)
    assert dialog._dirty is False


def test_same_value_recheck_does_not_mark_dirty(dialog):
    dialog.table.item(0, 0).setCheckState(Qt.Checked)  # already checked
    assert dialog._dirty is False


def test_reverting_to_saved_state_clears_dirty(dialog):
    # regression: uncheck then re-check the same box = no net change
    dialog.table.item(0, 0).setCheckState(Qt.Unchecked)
    assert dialog._dirty is True
    dialog.table.item(0, 0).setCheckState(Qt.Checked)
    assert dialog._dirty is False
    # mixed case: two flips, one reverted -> still dirty
    dialog.table.item(0, 0).setCheckState(Qt.Unchecked)
    dialog.table.item(1, 0).setCheckState(Qt.Unchecked)
    dialog.table.item(1, 0).setCheckState(Qt.Checked)
    assert dialog._dirty is True


def test_selection_plays_snippet(dialog):
    dialog.table.selectRow(1)
    assert dialog._player.played
    media, s, e = dialog._player.played[-1]
    assert (s, e) == (9.0, 9.4)


def test_unmute_all_then_rerender(dialog, monkeypatch):
    applied = []
    from wordmute_app.core import review as review_mod
    monkeypatch.setattr(review_mod, "apply_review", applied.append)

    dialog._set_all(False)
    assert all(not iv["muted"] for iv in dialog._data["intervals"])

    dialog._rerender()
    dialog._worker.wait(10000)
    dialog._worker = None  # signal delivery not pumped in offscreen test
    assert len(applied) == 1
    assert applied[0] is dialog._data


def test_scoped_reporter_isolates_rerender_from_queue():
    """Regression: a re-render running while the queue processes another
    item must not leak its engine events into the queue's reporter (the
    downloading card's status was flickering to re-render text), and
    queue events must not drive the dialog's progress."""
    import threading
    from wordmute_app.ui.review_dialog import _scoped_reporter

    queue_events = []
    progress = []
    me = threading.get_ident()

    # events from the re-render thread stay private to the dialog
    rep = _scoped_reporter(lambda e, d: queue_events.append(e), me,
                           progress.append)
    rep("mute_start", {"n": 3})
    rep("mute_progress", {"seconds": 1.5})
    assert queue_events == []
    assert progress == [1.5]

    # events from any OTHER thread pass through to the queue reporter
    # untouched and never touch the dialog progress
    rep = _scoped_reporter(lambda e, d: queue_events.append(e), me - 1,
                           progress.append)
    rep("mute_progress", {"seconds": 9.0})
    rep("transcribe_progress", {"seconds": 2.0})
    assert queue_events == ["mute_progress", "transcribe_progress"]
    assert progress == [1.5]


def test_missing_source_disables_rerender(qapp, review_file, monkeypatch,
                                          tmp_path):
    from wordmute_app.ui import review_dialog
    monkeypatch.setattr(review_dialog, "SnippetPlayer", DummyPlayer)
    (tmp_path / "v.mp4").unlink()
    d = review_dialog.ReviewDialog(review_file)
    assert not d.rerender_button.isEnabled()
    d.table.selectRow(0)
    assert not d._player.played  # no playback without source
