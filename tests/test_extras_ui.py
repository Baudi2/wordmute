"""Offscreen construction of the milestone-7 dialogs and i18n."""

import json


def test_tester_dialog_live_results(qapp, tmp_path):
    from wordmute_app.ui.tester_dialog import TesterDialog

    wl = tmp_path / "list.txt"
    wl.write_text("бог\nколд*\n*монстр*\nбоже мой\n", encoding="utf-8")
    d = TesterDialog([wl])
    d.input.setText("колдовать и демонстрация")
    text = d.results.toPlainText()
    assert "колд*" in text
    assert "*монстр*" in text
    assert "(no match)" in text  # "и"
    d.input.setText("боже мой")
    assert 'phrase "боже мой"' in d.results.toPlainText()


def test_transcript_dialog_search_and_export(qapp, tmp_path):
    from wordmute_app.ui.transcript_dialog import TranscriptDialog

    media = tmp_path / "v.mp4"
    words = [{"w": "привет", "s": 0.0, "e": 0.4},
             {"w": "мир", "s": 0.5, "e": 0.9},
             {"w": "финал", "s": 5.0, "e": 5.4}]
    (tmp_path / "v.mp4.words.json").write_text(json.dumps(words),
                                               encoding="utf-8")
    d = TranscriptDialog(media)
    assert d.table.rowCount() == 2  # two blocks (gap > 0.8s)
    d._filter("финал")
    assert d.table.isRowHidden(0)
    assert not d.table.isRowHidden(1)
    d._filter("")
    assert not d.table.isRowHidden(0)


def test_models_dialog_lists_status(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    d1 = tmp_path / "models--Systran--faster-whisper-base" / "blobs"
    d1.mkdir(parents=True)
    (d1 / "w.bin").write_bytes(b"x" * 100)
    from wordmute_app.ui.models_dialog import ModelsDialog

    d = ModelsDialog()
    rows = {d.table.item(r, 0).text(): d.table.item(r, 1).text()
            for r in range(d.table.rowCount())}
    assert rows["base"] == "downloaded"
    assert rows["large-v3"] == "not downloaded"


def test_history_dialog_populates(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import history
    from wordmute_app.ui.history_dialog import HistoryDialog

    history.append_history({"name": "v.mp4", "status": "ok", "muted": 5,
                            "plan": "whisper(small)", "output": "v.clean.mp4"})
    d = HistoryDialog()
    assert d.table.rowCount() == 1
    assert d.table.item(0, 1).text() == "v.mp4"
    assert d.table.item(0, 3).text() == "5"


def test_i18n_translates_and_falls_through():
    from wordmute_app.ui import i18n

    i18n.set_language("ru")
    try:
        assert i18n.tr("Start") == "Старт"
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
