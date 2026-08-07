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
    assert rows["base"] == "downloaded"
    assert rows["large-v3"] == "not downloaded"


def test_history_tab_populates(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import history
    from wordmute_app.ui.history_tab import HistoryTab

    history.append_history({"name": "v.mp4", "status": "ok", "muted": 5,
                            "plan": "whisper(small)", "output": "v.clean.mp4"})
    tab = HistoryTab()
    assert tab.table.rowCount() == 1
    assert tab.table.item(0, 1).text() == "v.mp4"
    assert tab.table.item(0, 3).text() == "5"


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
    w.table.item(0, 2).setText("done")
    w._clear_finished_rows()
    assert w.table.rowCount() == 1
    assert w.table.item(0, 0).text() == "b.mp4"


def test_main_window_has_tabs(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    titles = [w.tabs.tabText(i) for i in range(w.tabs.count())]
    assert titles == ["Queue", "Word Lists", "Transcript", "Models",
                      "History"]
    assert w.tabs.currentIndex() == 0
