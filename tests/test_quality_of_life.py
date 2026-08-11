"""v0.4.0 quality-of-life batch: keep-awake during runs, finish
notification, initial-window-size clamp, repair/disk in Models,
download-traffic stat in History."""

from pathlib import Path

import pytest


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.main_window import MainWindow
    return MainWindow()


# ------------------------------------------------------------ keep-awake
def test_keep_awake_calls_windows_api(monkeypatch):
    import ctypes
    from wordmute_app.core import power

    calls = []
    monkeypatch.setattr(ctypes.windll.kernel32, "SetThreadExecutionState",
                        calls.append, raising=False)
    power.keep_awake(True)
    power.keep_awake(False)
    assert len(calls) == 2
    on, off = (c.value for c in calls)
    assert on == power.ES_CONTINUOUS | power.ES_SYSTEM_REQUIRED
    assert off == power.ES_CONTINUOUS


def test_run_state_toggles_keep_awake(window, monkeypatch):
    from wordmute_app.core import power

    states = []
    monkeypatch.setattr(power, "keep_awake", states.append)
    window._set_running(True)
    window._set_running(False)
    assert states == [True, False]


# ---------------------------------------------------------- notification
def test_finish_notifies_when_in_background(window, monkeypatch):
    messages = []

    class FakeTray:
        def showMessage(self, title, text, *a):
            messages.append((title, text))

    window._tray = FakeTray()
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    window._on_all_finished(2, 3)
    assert messages and messages[0][0] == "WordMute"
    assert "2/3" in messages[0][1]


def test_finish_stays_quiet_when_window_active(window, monkeypatch):
    messages = []

    class FakeTray:
        def showMessage(self, *a):
            messages.append(a)

    window._tray = FakeTray()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window._on_all_finished(1, 1)
    assert messages == []


def test_finish_without_tray_does_not_crash(window, monkeypatch):
    window._tray = None
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    window._on_all_finished(1, 1)  # QApplication.alert path only


# --------------------------------------------------- models tab: disk/repair
@pytest.fixture
def models_tab(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    from wordmute_app.core import gpu, models
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    monkeypatch.setattr(models, "whisper_model_status", lambda: [
        {"model": "large-v3", "downloaded": True,
         "size_bytes": 3_000_000_000},
        {"model": "small", "downloaded": False, "size_bytes": None}])
    monkeypatch.setattr(models, "gigaam_cache_dirs",
                        lambda: [("x", 500_000_000)])
    from wordmute_app.ui.models_tab import ModelsTab
    tab = ModelsTab()
    yield tab
    tab.shutdown()


def test_runtime_disk_usage_walks_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from wordmute_app.core import runtime_env

    assert runtime_env.disk_usage() == 0   # nothing installed
    sub = runtime_env.runtime_dir() / "python" / "Lib"
    sub.mkdir(parents=True)
    (sub / "a.py").write_bytes(b"x" * 100)
    (runtime_env.runtime_dir() / "b.bin").write_bytes(b"y" * 23)
    assert runtime_env.disk_usage() == 123


def test_disk_label_combines_components(models_tab):
    from wordmute_app.core.models import fmt_size

    models_tab._on_disk_result(2_000_000_000)
    text = models_tab.disk_label.text()
    assert fmt_size(2_000_000_000) in text                    # runtime
    assert fmt_size(3_000_000_000) in text                    # whisper
    assert fmt_size(500_000_000) in text                      # gigaam
    assert fmt_size(5_500_000_000) in text                    # total


def test_repair_deletes_runtime_and_reopens_setup(models_tab, monkeypatch,
                                                  tmp_path):
    from wordmute_app.core import runtime_env
    from PySide6.QtWidgets import QMessageBox

    marker = runtime_env.runtime_dir() / "python" / "python.exe"
    marker.parent.mkdir(parents=True)
    marker.touch()
    opened = []
    monkeypatch.setattr(models_tab, "_open_components",
                        lambda: opened.append(True))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    models_tab._repair_components()
    assert not runtime_env.runtime_dir().exists()
    assert opened == [True]


def test_repair_declined_keeps_runtime(models_tab, monkeypatch):
    from wordmute_app.core import runtime_env
    from PySide6.QtWidgets import QMessageBox

    runtime_env.runtime_dir().mkdir(parents=True)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)
    models_tab._repair_components()
    assert runtime_env.runtime_dir().exists()


# ------------------------------------------------------------- traffic
def test_month_traffic_sums_current_month_only(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import json
    from wordmute_app.core import history

    history.append_history({"name": "a", "downloaded_bytes": 700})
    history.append_history({"name": "b", "downloaded_bytes": 300})
    history.append_history({"name": "old-style-no-field"})
    # a record from another month is ignored
    with history.history_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": "1999-01-02T10:00:00",
                            "downloaded_bytes": 10 ** 9}) + "\n")
    assert history.month_traffic() == 1000


def test_worker_records_download_bytes(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from wordmute_app.core import downloader, history
    from wordmute_app.core.jobs import QueueItem
    from test_worker import make_worker

    def fake_download(url, spec, dest_dir, progress=None, cancelled=None,
                      cookies=None):
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / "video.mp4"
        p.write_bytes(b"x" * 4096)
        return p

    monkeypatch.setattr(downloader, "download", fake_download)
    worker, log = make_worker(
        [QueueItem(kind="url", url="https://e.com/v", title="V")],
        monkeypatch)
    worker._download_dir = tmp_path / "dl"
    worker.run()
    assert log["files"] == [(0, True, "")]
    records = history.load_history()
    assert records[0]["downloaded_bytes"] == 4096
    assert history.month_traffic() == 4096


def test_history_footer_shows_month_traffic(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import history
    from wordmute_app.core.models import fmt_size
    from wordmute_app.ui.history_tab import HistoryTab

    tab = HistoryTab()
    assert tab.traffic_label.text() == ""      # nothing downloaded yet
    history.append_history({"name": "v.mp4", "status": "ok", "muted": 0,
                            "plan": "whisper(s)",
                            "downloaded_bytes": 123_456_789})
    tab.refresh()
    assert fmt_size(123_456_789) in tab.traffic_label.text()


# ---------------------------------------------------------- self-update
def _fake_release(monkeypatch, tag, url="https://x/rel"):
    import io
    import urllib.request
    import json as json_mod

    def fake_urlopen(request, timeout=0):
        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(json_mod.dumps(
            {"tag_name": tag, "html_url": url}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def test_app_update_detected(monkeypatch):
    import wordmute_app
    from wordmute_app.core import updates

    monkeypatch.setattr(wordmute_app, "__version__", "0.3.0")
    _fake_release(monkeypatch, "v9.9.9")
    info = updates.check_app_update()
    assert info["update"] is True
    assert info["latest"] == "9.9.9"
    assert info["url"] == "https://x/rel"


def test_app_update_current_and_offline(monkeypatch):
    import urllib.request
    import wordmute_app
    from wordmute_app.core import updates

    monkeypatch.setattr(wordmute_app, "__version__", "9.9.9")
    _fake_release(monkeypatch, "v0.3.0")
    assert updates.check_app_update()["update"] is False

    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    info = updates.check_app_update()   # never raises
    assert info["update"] is False and info["latest"] is None


def test_startup_check_notifies_via_tray(window, monkeypatch):
    messages = []

    class FakeTray:
        class _Sig:
            def connect(self, *a):
                pass

            def disconnect(self, *a):
                pass
        messageClicked = _Sig()

        def showMessage(self, title, text, *a):
            messages.append(text)

    window._tray = FakeTray()
    window._on_app_update_result(
        {"update": True, "current": "0.3.0", "latest": "0.4.0",
         "url": "https://x/rel"})
    assert messages and "0.4.0" in messages[0]
    assert window._update_url == "https://x/rel"
    # no update -> silent
    messages.clear()
    window._on_app_update_result({"update": False})
    assert messages == []


# ------------------------------------------------- setup: model choice
def test_setup_dialog_model_choice(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    from wordmute_app.core import config, gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    from wordmute_app.ui.setup_dialog import SetupDialog

    d = SetupDialog(first_run=True)
    # default reflects settings (large-v3), radios are their own group:
    # picking a model must not uncheck the CPU/GPU flavor
    assert d.model_radios["large-v3"].isChecked()
    flavor_before = d.cpu_radio.isChecked()
    d.model_radios["medium"].setChecked(True)
    assert d.cpu_radio.isChecked() == flavor_before
    assert not d.model_radios["large-v3"].isChecked()
    d.accept()
    assert config.load_settings()["model"] == "medium"

    # repair mode has no model choice and accept() must not crash
    d2 = SetupDialog(first_run=False)
    assert d2.model_radios == {}
    d2.accept()
    assert config.load_settings()["model"] == "medium"


# ------------------------------------------------------------ size clamp
def test_initial_size_clamps_to_small_screens():
    from wordmute_app.ui.main_window import _initial_size

    assert _initial_size(1920, 1040) == (960, 720)   # big screen: as-is
    assert _initial_size(911, 512) == (887, 464)     # 1366x768 @150%
    assert _initial_size(0, 0) == (960, 720)         # unknown screen
    # the floor keeps the window usable even on absurd geometry
    assert _initial_size(300, 200) == (480, 360)
