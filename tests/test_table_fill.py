"""Opening the History tab froze the window for 3.5 s (200 records):
a header section in ResizeToContents re-measures its whole column
after every setItem, so a fill cost rows². HoverRowTable.filling()
parks those sections as Fixed for the duration of a fill — 0.04 s for
the same history, 0.02 s instead of 11.7 s for a 300-row Review table
refilled while shown. Every table fill must run inside it."""

import contextlib
import json

import pytest
from PySide6.QtWidgets import QHeaderView, QTableWidgetItem

from wordmute_app.core import history, review
from wordmute_app.ui.hover_table import HoverRowTable

FIT = QHeaderView.ResizeToContents


def modes(table):
    header = table.horizontalHeader()
    return [header.sectionResizeMode(c) for c in range(table.columnCount())]


def test_filling_parks_only_the_fitted_sections(qapp):
    table = HoverRowTable(0, 3)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, FIT)
    header.setSectionResizeMode(1, QHeaderView.Stretch)
    header.setSectionResizeMode(2, QHeaderView.Fixed)
    with table.filling():
        assert modes(table) == [QHeaderView.Fixed, QHeaderView.Stretch,
                                QHeaderView.Fixed]
    assert modes(table) == [FIT, QHeaderView.Stretch, QHeaderView.Fixed]


def test_filling_restores_the_header_when_the_fill_fails(qapp):
    table = HoverRowTable(0, 2)
    table.horizontalHeader().setSectionResizeMode(FIT)
    with pytest.raises(RuntimeError):
        with table.filling():
            raise RuntimeError("bad record")
    assert modes(table) == [FIT, FIT]


@pytest.fixture
def fits_seen(monkeypatch):
    """Records, for every setItem on any HoverRowTable, whether some
    section was still fitting itself to the contents at that moment."""
    seen = []
    original = HoverRowTable.setItem

    def spy(self, row, col, item):
        seen.append(FIT in modes(self))
        return original(self, row, col, item)

    monkeypatch.setattr(HoverRowTable, "setItem", spy)
    return seen


def test_history_fills_without_remeasuring(qapp, tmp_path, monkeypatch,
                                           fits_seen):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.ui.history_tab import HistoryTab

    for n in range(30):
        history.append_history({"name": f"v{n}.mp4", "status": "ok",
                                "muted": n, "plan": "whisper(small)"})
    tab = HistoryTab()
    tab.show()
    tab.refresh()
    assert len(fits_seen) == 2 * 30 * 5 and not any(fits_seen)
    assert FIT in modes(tab.table)          # fitted again afterwards
    tab.close()


def test_review_fills_without_remeasuring(qapp, tmp_path, monkeypatch,
                                          fits_seen):
    from wordmute_app.ui import review_dialog as rd

    class NoPlayer:
        def play(self, *a):
            pass

        def stop(self):
            pass

        def dispose(self):
            pass

    monkeypatch.setattr(rd, "SnippetPlayer", NoPlayer)
    src, out = tmp_path / "v.mp4", tmp_path / "v.clean.mp4"
    src.write_bytes(b"x")
    out.write_bytes(b"x")
    sidecar = review.save_review(src, out, 100, [
        {"s": 5.0 + i * 10, "e": 5.5 + i * 10, "text": f"w{i}", "pass": 1,
         "engine": "whisper", "muted": True} for i in range(20)])
    dialog = rd.ReviewDialog(sidecar)
    dialog.show()
    dialog._fill_table()
    assert len(fits_seen) == 2 * 20 * 6 and not any(fits_seen)
    assert FIT in modes(dialog.table)
    dialog.close()


def test_transcript_fills_without_remeasuring(qapp, tmp_path, monkeypatch,
                                              fits_seen):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from wordmute_app.engine import wordmute as engine
    from wordmute_app.ui.transcript_tab import TranscriptTab

    media = tmp_path / "v.mp4"
    media.write_bytes(b"x")
    words = [{"w": f"слово{i}", "s": i * 3.0, "e": i * 3.0 + 0.4}
             for i in range(40)]
    engine._cache_path(media, "whisper").write_text(
        json.dumps(words, ensure_ascii=False), encoding="utf-8")
    tab = TranscriptTab()
    tab.show()
    tab.load_media(media)
    assert tab.table.rowCount() > 1
    assert len(fits_seen) == 2 * tab.table.rowCount()
    assert not any(fits_seen)
    tab.close()


def test_add_url_fills_without_remeasuring(qapp, fits_seen):
    from wordmute_app.ui.url_dialog import AddUrlDialog

    dialog = AddUrlDialog(url="https://example.com/v", auto_fetch=False)
    dialog.show()
    formats = [{"format_id": str(i), "ext": "mp4", "vcodec": "avc1",
                "acodec": "mp4a", "height": 144 * (i + 1), "fps": 25,
                "filesize": (i + 1) * 50 * 1024 ** 2} for i in range(6)]
    dialog._on_formats_ready({"title": "v", "duration": 60,
                              "url": "https://example.com/v",
                              "formats": formats})
    assert len(fits_seen) == 7 * 6 and not any(fits_seen)   # «best» + 6
    dialog.close()


def test_columns_end_up_as_wide_as_before(qapp, tmp_path, monkeypatch):
    """Same widths as the old fill that measured after every cell."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.ui.history_tab import HistoryTab

    for n in range(12):
        history.append_history({
            "name": f"Лекция {n} — очень длинное название.mp4",
            "status": "ok" if n % 3 else "error", "muted": n * 7,
            "plan": "gigaam(v3_rnnt) -> gigaam(v3_rnnt) -> whisper(large-v3)"})

    def widths():
        tab = HistoryTab()
        tab.resize(900, 600)
        tab.show()
        for _ in range(4):
            qapp.processEvents()
        result = [tab.table.columnWidth(c)
                  for c in range(tab.table.columnCount())]
        tab.close()
        return result

    fast = widths()
    monkeypatch.setattr(HoverRowTable, "filling",
                        contextlib.contextmanager(lambda self: (yield)))
    assert widths() == fast


def test_a_new_cell_still_refits_its_column(qapp):
    """Outside a fill the header behaves as before."""
    table = HoverRowTable(1, 1)
    table.horizontalHeader().setSectionResizeMode(FIT)
    table.show()
    table.setItem(0, 0, QTableWidgetItem("a"))
    qapp.processEvents()
    narrow = table.columnWidth(0)
    table.setItem(0, 0, QTableWidgetItem("a much, much longer cell text"))
    qapp.processEvents()
    assert table.columnWidth(0) > narrow
    table.close()
