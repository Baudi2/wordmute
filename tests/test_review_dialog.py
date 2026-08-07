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


def test_missing_source_disables_rerender(qapp, review_file, monkeypatch,
                                          tmp_path):
    from wordmute_app.ui import review_dialog
    monkeypatch.setattr(review_dialog, "SnippetPlayer", DummyPlayer)
    (tmp_path / "v.mp4").unlink()
    d = review_dialog.ReviewDialog(review_file)
    assert not d.rerender_button.isEnabled()
    d.table.selectRow(0)
    assert not d._player.played  # no playback without source
