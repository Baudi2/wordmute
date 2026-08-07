"""Offscreen construction of the main window and queue behavior."""


def test_main_window_constructs_and_filters_queue(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    media = tmp_path / "a.mp4"
    clean = tmp_path / "a.clean.mp4"
    text = tmp_path / "notes.txt"
    for f in (media, clean, text):
        f.touch()

    w._add_files([media, clean, text, media])  # dupes/clean/non-media dropped
    assert w.table.rowCount() == 1
    assert w.table.item(0, 0).text() == "a.mp4"
    assert w.table.item(0, 1).text() == "queued"

    w.table.selectRow(0)
    w._remove_selected()
    assert w.table.rowCount() == 0


def test_settings_saved_on_close(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import config
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    w.model_combo.setCurrentText("small")
    w.english_check.setChecked(True)
    w.close()

    s = config.load_settings()
    assert s["model"] == "small"
    assert s["use_english"] is True
