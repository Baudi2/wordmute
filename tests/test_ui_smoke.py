"""Offscreen construction of the main window, queue behavior, plan
builder, and settings dialog."""


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
    assert w.table.item(0, 2).text() == "queued"

    w.table.selectRow(0)
    w._remove_selected()
    assert w.table.rowCount() == 0


def test_folder_add_expands_media(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.ui.main_window import MainWindow

    folder = tmp_path / "videos"
    folder.mkdir()
    (folder / "b.mp4").touch()
    (folder / "a.mkv").touch()
    (folder / "a.clean.mkv").touch()
    (folder / "junk.txt").touch()

    w = MainWindow()
    w._add_files([folder])
    assert [w.table.item(r, 0).text() for r in range(w.table.rowCount())] \
        == ["a.mkv", "b.mp4"]


def test_settings_saved_on_close(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import config
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    assert w.plan.engines() == ["whisper", "whisper"]  # default plan
    w.plan.set_engines(["gigaam", "gigaam", "whisper"])
    w.english_check.setChecked(True)
    w.force_passes_check.setChecked(True)
    w.close()

    s = config.load_settings()
    assert s["plan"] == ["gigaam", "gigaam", "whisper"]
    assert s["use_english"] is True
    assert s["force_passes"] is True


def test_plan_widget_add_remove_reorder(qapp):
    from wordmute_app.ui.plan_widget import PassPlanWidget

    p = PassPlanWidget()
    p.add_pass("gigaam")
    p.add_pass("gigaam")
    p.add_pass("whisper")
    assert p.engines() == ["gigaam", "gigaam", "whisper"]
    assert p.list.item(2).text() == "3. Whisper"

    p.list.setCurrentRow(2)
    p.move_selected(-1)
    assert p.engines() == ["gigaam", "whisper", "gigaam"]
    assert p.list.item(1).text() == "2. Whisper"
    p.move_selected(-1)
    p.move_selected(-1)  # already at top: no-op
    assert p.engines() == ["whisper", "gigaam", "gigaam"]

    p.list.setCurrentRow(0)
    p.remove_selected()
    assert p.engines() == ["gigaam", "gigaam"]
    assert p.list.item(0).text() == "1. GigaAM"


def test_settings_dialog_values(qapp):
    from wordmute_app.core.config import DEFAULT_SETTINGS
    from wordmute_app.ui.settings_dialog import SettingsDialog

    d = SettingsDialog(dict(DEFAULT_SETTINGS))
    d.model_combo.setCurrentText("medium")
    d.gigaam_combo.setCurrentText("v3_e2e_ctc")
    d.device_combo.setCurrentText("cpu")
    d.pad_spin.setValue(250)
    d.language_edit.setText("en")
    d.vad_check.setChecked(False)
    v = d.values()
    assert v["model"] == "medium"
    assert v["gigaam_model"] == "v3_e2e_ctc"
    assert v["device"] == "cpu"
    assert v["pad_ms"] == 250
    assert v["language"] == "en"
    assert v["vad"] is False
    assert v["output_mode"] == "beside"


def test_settings_dialog_folder_mode_requires_dir(qapp, tmp_path):
    from wordmute_app.core.config import DEFAULT_SETTINGS
    from wordmute_app.ui.settings_dialog import SettingsDialog

    d = SettingsDialog(dict(DEFAULT_SETTINGS))
    d.folder_radio.setChecked(True)
    assert d.values()["output_mode"] == "beside"  # no dir given
    d.output_dir_edit.setText(str(tmp_path))
    assert d.values()["output_mode"] == "folder"
    assert d.values()["output_dir"] == str(tmp_path)
