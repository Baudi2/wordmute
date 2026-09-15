import os

import pytest

# tests must never hit the network: the startup self-update check is
# disabled globally (it spawns a delayed worker thread otherwise)
os.environ.setdefault("WORDMUTE_NO_UPDATE_CHECK", "1")
# bulk file adds probe synchronously in tests — a background probe
# thread living past its test crashes Qt teardown at session end
os.environ.setdefault("WORDMUTE_SYNC_PROBE", "1")
# the profile as it was before any test isolated it: the managed runtime
# (and the FFmpeg build it installs) lives under it
REAL_LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")


@pytest.fixture(scope="session")
def ffmpeg_builds():
    """[(folder, version line)] for every distinct FFmpeg the app can end
    up running: the one on PATH and the managed runtime's. The FFmpeg 9
    break stayed hidden because the real-ffmpeg tests only ever ran on
    PATH's 8.1.2."""
    import shutil
    import subprocess
    from pathlib import Path

    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    folders = []
    found = shutil.which("ffmpeg")
    if found:
        folders.append(Path(found).parent)
    if REAL_LOCALAPPDATA:
        runtime = Path(REAL_LOCALAPPDATA) / "WordMute" / "runtime" / "ffmpeg"
        if (runtime / exe).exists():
            folders.append(runtime)
    builds, seen = [], set()
    for folder in folders:
        try:
            line = subprocess.run([str(folder / exe), "-version"],
                                  capture_output=True, text=True,
                                  timeout=30).stdout.splitlines()[0]
        except (OSError, IndexError, subprocess.TimeoutExpired):
            continue
        if line not in seen:
            seen.add(line)
            builds.append((str(folder), line))
    return builds


@pytest.fixture(autouse=True)
def isolated_app_data(tmp_path_factory, monkeypatch):
    """No test may read or write the user's real WordMute data: the
    worker tests appended fake runs to %APPDATA%\\WordMute\\history.jsonl
    and a Models-tab test saved its fixture into the real settings.json.
    Every test gets its own APPDATA / LOCALAPPDATA; a test that sets its
    own with monkeypatch.setenv still wins."""
    root = tmp_path_factory.mktemp("appdata")
    monkeypatch.setenv("APPDATA", str(root / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(root / "Local"))


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """A confirmation that actually opens would block the whole suite
    forever (exec() waits for a click). Default every ConfirmDialog to
    Cancel; a test that wants the destructive path opts in with the
    `confirm_yes` fixture."""
    from PySide6.QtWidgets import QDialog
    from wordmute_app.ui import dialogs
    monkeypatch.setattr(dialogs.ConfirmDialog, "exec",
                        lambda self: QDialog.Rejected, raising=False)


@pytest.fixture(autouse=True)
def no_url_probe(monkeypatch):
    """URL cards now fetch their title/poster via yt-dlp right after
    being added; under WORDMUTE_SYNC_PROBE that call would run inline
    and hit the network. Tests get an empty probe by default; a test
    exercising the feature re-patches probe_url itself."""
    from wordmute_app.core import downloader
    monkeypatch.setattr(
        downloader, "probe_url",
        lambda url, cookies=None: {"title": "", "duration": None,
                                   "thumbnail_url": ""},
        raising=False)


@pytest.fixture
def confirm_yes(monkeypatch):
    """Answer every confirmation with its primary (accept) button."""
    from PySide6.QtWidgets import QDialog
    from wordmute_app.ui import dialogs
    monkeypatch.setattr(dialogs.ConfirmDialog, "exec",
                        lambda self: QDialog.Accepted, raising=False)
