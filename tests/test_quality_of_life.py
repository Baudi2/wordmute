"""v0.4.0 quality-of-life batch: keep-awake during runs, finish
notification, initial-window-size clamp."""

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


# ------------------------------------------------------------ size clamp
def test_initial_size_clamps_to_small_screens():
    from wordmute_app.ui.main_window import _initial_size

    assert _initial_size(1920, 1040) == (960, 720)   # big screen: as-is
    assert _initial_size(911, 512) == (887, 464)     # 1366x768 @150%
    assert _initial_size(0, 0) == (960, 720)         # unknown screen
    # the floor keeps the window usable even on absurd geometry
    assert _initial_size(300, 200) == (480, 360)
