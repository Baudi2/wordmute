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


# ------------------------------------------------------------ size clamp
def test_initial_size_clamps_to_small_screens():
    from wordmute_app.ui.main_window import _initial_size

    assert _initial_size(1920, 1040) == (960, 720)   # big screen: as-is
    assert _initial_size(911, 512) == (887, 464)     # 1366x768 @150%
    assert _initial_size(0, 0) == (960, 720)         # unknown screen
    # the floor keeps the window usable even on absurd geometry
    assert _initial_size(300, 200) == (480, 360)
