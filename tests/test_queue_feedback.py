"""Adding files must never be silent: a dropped .clean result or a
non-media file used to vanish without a word, and the queue's setup
line now says where results land."""

from wordmute_app.core.jobs import expand_inputs


def _window(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow
    return MainWindow()


def test_expand_inputs_reports_what_it_skips(tmp_path):
    clean = tmp_path / "v.clean.mp4"
    clean.touch()
    text = tmp_path / "notes.txt"
    text.touch()
    folder = tmp_path / "done"
    folder.mkdir()
    (folder / "a.mp4").touch()
    (folder / "a.clean.mp4").touch()
    (folder / "readme.txt").touch()          # a folder's other files: normal
    skipped = {"clean": [], "not_media": []}
    assert expand_inputs([clean, text, folder], skipped) == [folder / "a.mp4"]
    assert skipped["clean"] == [clean, folder / "a.clean.mp4"]
    assert skipped["not_media"] == [text]


def test_dropping_a_clean_result_gives_feedback(qapp, tmp_path, monkeypatch):
    w = _window(tmp_path, monkeypatch)
    clean = tmp_path / "lecture.clean.mp4"
    clean.touch()
    w._add_files([clean])
    assert w.queue.count() == 0
    assert "already-processed" in w.status_label.text()
    assert "add the original video" in w.status_label.text()
    # and the same file twice is reported, not silently dropped
    src = tmp_path / "lecture.mp4"
    src.touch()
    w._add_files([src])
    w._add_files([src])
    assert w.queue.count() == 1
    assert "already in the queue" in w.status_label.text()


def test_setup_summary_names_the_output_location(qapp, tmp_path,
                                                 monkeypatch):
    w = _window(tmp_path, monkeypatch)
    assert "Output: next to the source" in w.setup_summary.text()
    w._settings["output_mode"] = "folder"
    w._settings["output_dir"] = r"D:\clean"
    w._update_setup_summary()
    assert r"Output: D:\clean" in w.setup_summary.text()
