"""Full speed in the background. On a laptop WordMute crawled while
it sat behind the browser and leapt ahead by minutes when clicked:
Windows power throttling (EcoQoS) parks background processes on the
efficient cores. A run now opts the process — and every child it
spawns — out of throttling, and hands it back when the run ends."""

import subprocess
import sys

import pytest

from wordmute_app.core import power

windows_only = pytest.mark.skipif(sys.platform != "win32",
                                  reason="Windows power throttling API")


@pytest.fixture
def system_managed():
    yield
    power.full_speed(False)
    assert power.throttling_state() == (0, 0)


@windows_only
def test_a_run_opts_the_process_out_and_back_in(system_managed):
    assert power.full_speed(True)
    # EXECUTION_SPEED in the control mask, clear in the state mask:
    # «never throttle» in Windows' terms
    assert power.throttling_state() == (
        power.PROCESS_POWER_THROTTLING_EXECUTION_SPEED, 0)
    assert power.full_speed(False)
    assert power.throttling_state() == (0, 0)      # back to the system


@windows_only
def test_children_started_during_a_run_run_at_full_speed(system_managed):
    power.install_child_full_speed()
    power.full_speed(True)
    child = subprocess.Popen([sys.executable, "-c",
                              "import time; time.sleep(5)"])
    try:
        assert power.throttling_state(child._handle) == (
            power.PROCESS_POWER_THROTTLING_EXECUTION_SPEED, 0)
    finally:
        child.kill()
        child.wait()
    power.full_speed(False)
    idle = subprocess.Popen([sys.executable, "-c",
                             "import time; time.sleep(5)"])
    try:            # outside a run a child is left to Windows
        assert power.throttling_state(idle._handle) == (0, 0)
    finally:
        idle.kill()
        idle.wait()


def test_the_window_switches_it_with_the_run(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus", lambda: [])
    calls = []
    monkeypatch.setattr(power, "full_speed", lambda on: calls.append(on))
    monkeypatch.setattr(power, "keep_awake", lambda on: None)
    from wordmute_app.ui.main_window import MainWindow
    window = MainWindow()
    window._set_running(True)
    window._set_running(False)
    window.close()
    assert calls == [True, False]
