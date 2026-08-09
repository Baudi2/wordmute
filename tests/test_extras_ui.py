"""Offscreen tests for the tool tabs and i18n."""

import json


def make_wordlists_tab(qapp, tmp_path):
    from wordmute_app.ui.wordlists_tab import WordListsTab

    ru = tmp_path / "words_russian.txt"
    ru.write_text("бог\nколд*\n*монстр*\nбоже мой\n", encoding="utf-8")
    en = tmp_path / "words_english.txt"
    en.write_text("god\n", encoding="utf-8")
    return WordListsTab({"russian": ru, "english": en}), ru, en


def test_wordlists_editor_loads_and_counts(qapp, tmp_path):
    tab, ru, _ = make_wordlists_tab(qapp, tmp_path)
    assert "бог" in tab.editor.toPlainText()
    assert tab.count_label.text() == "4 entries"
    assert not tab.has_unsaved()


def test_wordlists_save_runs_tidy(qapp, tmp_path):
    tab, ru, _ = make_wordlists_tab(qapp, tmp_path)
    tab.editor.clear()
    tab.editor.insertPlainText("Ёлка\nелка\nбог\n")  # as if typed
    assert tab.has_unsaved()
    tab._save()
    assert ru.read_text(encoding="utf-8") == "бог\nелка\n"
    assert not tab.has_unsaved()
    assert "1 duplicate(s) merged" in tab.status_label.text()


def test_wordlists_switch_lists(qapp, tmp_path):
    tab, _, en = make_wordlists_tab(qapp, tmp_path)
    tab.list_combo.setCurrentIndex(1)  # english, no unsaved changes
    assert tab.editor.toPlainText().strip() == "god"


def test_wordlists_tester_inline(qapp, tmp_path):
    tab, _, _ = make_wordlists_tab(qapp, tmp_path)
    tab.tester_input.setText("колдовать и демонстрация")
    text = tab.tester_results.toPlainText()
    assert "колд*" in text
    assert "*монстр*" in text
    assert "(no match)" in text  # "и"
    tab.tester_input.setText("боже мой")
    assert 'phrase "боже мой"' in tab.tester_results.toPlainText()


def test_transcript_tab_search_and_load(qapp, tmp_path):
    from wordmute_app.ui.transcript_tab import TranscriptTab

    media = tmp_path / "v.mp4"
    words = [{"w": "привет", "s": 0.0, "e": 0.4},
             {"w": "мир", "s": 0.5, "e": 0.9},
             {"w": "финал", "s": 5.0, "e": 5.4}]
    (tmp_path / "v.mp4.words.json").write_text(json.dumps(words),
                                               encoding="utf-8")
    tab = TranscriptTab()
    assert not tab.export_button.isEnabled()
    tab.load_media(media)
    assert tab.table.rowCount() == 2  # two blocks (gap > 0.8s)
    assert tab.export_button.isEnabled()
    tab._filter("финал")
    assert tab.table.isRowHidden(0)
    assert not tab.table.isRowHidden(1)


def test_transcript_tab_missing_cache_message(qapp, tmp_path):
    from wordmute_app.ui.transcript_tab import TranscriptTab

    tab = TranscriptTab()
    tab.load_media(tmp_path / "nope.mp4")
    assert "cached transcript" in tab.status_label.text()


def test_models_tab_lists_status(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    d1 = tmp_path / "models--Systran--faster-whisper-base" / "blobs"
    d1.mkdir(parents=True)
    (d1 / "w.bin").write_bytes(b"x" * 100)
    from wordmute_app.ui.models_tab import ModelsTab

    tab = ModelsTab()
    rows = {tab.table.item(r, 0).text(): tab.table.item(r, 1).text()
            for r in range(tab.table.rowCount())}
    assert rows["base"] == "downloaded ✓"
    assert rows["large-v3"] == "not downloaded"
    # per-row action buttons
    buttons = {tab.table.item(r, 0).text():
               tab.table.cellWidget(r, 3).text()
               for r in range(tab.table.rowCount())}
    assert buttons["base"] == "Delete"
    assert buttons["large-v3"] == "Download"


def test_history_tab_populates(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import history
    from wordmute_app.ui.history_tab import HistoryTab

    history.append_history({"name": "v.mp4", "status": "ok", "muted": 5,
                            "plan": "whisper(small)", "output": "v.clean.mp4"})
    history.append_history({"name": "b.mp4", "status": "error",
                            "error": "boom", "muted": 0,
                            "plan": "gigaam(v3) -> gigaam(v3) -> whisper(s)"})
    tab = HistoryTab()
    assert tab.table.rowCount() == 2
    # most recent first; status is a ✓/✗ glyph, plan is compacted
    assert tab.table.item(0, 1).text() == "b.mp4"
    assert tab.table.item(0, 2).text() == "✕"
    assert tab.table.item(0, 2).toolTip() == "boom"
    assert tab.table.item(0, 4).text() == "GigaAM ×2 → Whisper"
    assert tab.table.item(1, 2).text() == "✓"
    assert tab.table.item(1, 3).text() == "5"
    assert tab.table.item(1, 4).text() == "Whisper"
    # width diet: no row-number gutter, File stretches, no Output column
    assert not tab.table.verticalHeader().isVisible()
    assert tab.table.columnCount() == 5
    assert tab.folder_button.text()


def test_hover_row_table_paints_whole_row(qapp):
    from PySide6.QtWidgets import QTableWidgetItem

    from wordmute_app.ui.hover_table import HoverRowTable
    from wordmute_app.ui.theme import hover_color

    t = HoverRowTable(2, 3)
    for r in range(2):
        for c in range(3):
            t.setItem(r, c, QTableWidgetItem(f"{r}{c}"))

    t._set_hover(0)
    assert all(t.item(0, c).background().color() == hover_color()
               for c in range(3))
    t._set_hover(1)  # row 0 cleared, row 1 tinted
    assert all(t.item(1, c).background().color() == hover_color()
               for c in range(3))
    assert t.item(0, 0).background().color() != hover_color() or \
        t.item(0, 0).background().style() == 0  # cleared brush
    t.setRowCount(0)
    assert t._hover_row == -1


def test_i18n_translates_and_falls_through():
    from wordmute_app.ui import i18n

    i18n.set_language("ru")
    try:
        assert i18n.tr("Start") == "Старт"
        assert i18n.tr("Queue") == "Очередь"
        assert i18n.tr("untranslated string") == "untranslated string"
    finally:
        i18n.set_language("en")
    assert i18n.tr("Start") == "Start"


def test_watch_flow_scan_and_autoclear(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    a = tmp_path / "a.mp4"
    a.touch()
    b = tmp_path / "b.mp4"
    b.touch()
    w._add_files([a, b])
    w._card(0).set_status("done")
    w._clear_finished_rows()
    assert w.queue.count() == 1
    assert w._items()[0].display_name == "b.mp4"


def test_queue_reorder_rebuilds_cards_with_state(qapp, tmp_path,
                                                 monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    a = tmp_path / "a.mp4"
    a.touch()
    b = tmp_path / "b.mp4"
    b.touch()
    w._add_files([a, b])
    w._apply_status(0, "done → a.clean.mp4", state="ok")

    # takeItem/insertItem destroys the card widget, exactly like a
    # real drag-move does
    moved = w.queue.takeItem(0)
    w.queue.insertItem(1, moved)
    assert w.queue.itemWidget(moved) is None
    w._restore_cards()

    assert [it.display_name for it in w._items()] == ["b.mp4", "a.mp4"]
    assert w.status_text(0) == "queued"
    assert w.status_text(1) == "done → a.clean.mp4"
    assert w._card(1).status_label.property("state") == "ok"


def test_start_skips_already_done_rows(qapp, tmp_path, monkeypatch):
    # regression: Start used to reprocess the whole queue, re-running
    # files that had already completed in a previous run
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui import main_window as mw

    captured = {}

    class DummySignal:
        def connect(self, *a, **k):
            pass

    class FakeWorker:
        def __init__(self, items, *args, **kwargs):
            captured["items"] = list(items)
            self.engine_event = DummySignal()
            self.file_started = DummySignal()
            self.file_finished = DummySignal()
            self.all_finished = DummySignal()

        def start(self):
            pass

    monkeypatch.setattr(mw, "ProcessWorker", FakeWorker)
    w = mw.MainWindow()
    a = tmp_path / "a.mp4"
    a.touch()
    b = tmp_path / "b.mp4"
    b.touch()
    w._add_files([a, b])
    w._card(0).set_status("done → a.clean.mp4", state="ok")

    w._start()
    assert [it.display_name for it in captured["items"]] == ["b.mp4"]
    assert w._active_rows == [1]
    assert w._map_row(0) == 1  # worker index 0 -> queue row 1
    # the finished card was left alone
    assert w.status_text(0).startswith("done")
    w._worker = None  # fake worker: nothing to wait for on close


def test_main_window_has_tabs(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    titles = [w.tabs.tabText(i) for i in range(w.tabs.count())]
    assert titles == ["Queue", "Word Lists", "Transcript", "Models",
                      "History", "Settings"]
    assert w.tabs.currentIndex() == 0
