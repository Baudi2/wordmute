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


def test_warning_bar_reflects_plan_and_device(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus",
                        lambda: [gpu.GpuInfo("RTX 4060", 8188)])
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    assert not w.warnings_label.isVisible()  # whisper plan fits, no gigaam

    w.plan.add_pass("gigaam")  # no token saved -> setup hint appears
    assert "GigaAM Setup" in w.warnings_label.text()

    w._settings["device"] = "cpu"
    w._refresh_warnings()
    assert "CPU mode" in w.warnings_label.text()


def test_warning_bar_cuda_without_gpu(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow

    w = MainWindow()
    assert "will fail" in w.warnings_label.text()


def test_add_url_button_click_opens_dialog_with_empty_url(qapp, tmp_path,
                                                          monkeypatch):
    # regression: clicked(checked) used to leak False into the url arg
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.ui import main_window as mw

    opened = []

    class FakeDialog:
        def __init__(self, parent=None, url="", cookies=None):
            assert isinstance(url, str), f"url must be str, got {url!r}"
            opened.append(url)

        def exec(self):
            return 0

    monkeypatch.setattr(mw, "AddUrlDialog", FakeDialog)
    w = mw.MainWindow()
    w.add_url_button.click()
    assert opened == [""]
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


def test_settings_tab_applies_immediately(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import config
    from wordmute_app.ui.settings_tab import SettingsTab

    settings = config.load_settings()
    tab = SettingsTab(settings)
    tab.model_combo.setCurrentText("medium")
    tab.gigaam_combo.setCurrentText("v3_e2e_ctc")
    tab.device_combo.setCurrentText("cpu")
    tab.pad_spin.setValue(250)
    tab.language_edit.setText("en")
    tab.vad_check.setChecked(False)
    tab.cookies_edit.setText(r"C:\cookies\c.txt")

    # every change lands in the dict AND on disk without any OK button
    assert settings["model"] == "medium"
    assert settings["gigaam_model"] == "v3_e2e_ctc"
    assert settings["device"] == "cpu"
    assert settings["pad_ms"] == 250
    assert settings["language"] == "en"
    assert settings["vad"] is False
    assert settings["cookies_file"] == r"C:\cookies\c.txt"
    stored = config.load_settings()
    assert stored["model"] == "medium"
    assert stored["cookies_file"] == r"C:\cookies\c.txt"


def test_settings_tab_folder_mode_requires_dir(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import config
    from wordmute_app.ui.settings_tab import SettingsTab

    settings = config.load_settings()
    tab = SettingsTab(settings)
    tab.folder_radio.setChecked(True)
    assert settings["output_mode"] == "beside"  # no dir given
    tab.output_dir_edit.setText(str(tmp_path))
    assert settings["output_mode"] == "folder"
    assert settings["output_dir"] == str(tmp_path)
