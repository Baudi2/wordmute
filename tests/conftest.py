import os

import pytest

# tests must never hit the network: the startup self-update check is
# disabled globally (it spawns a delayed worker thread otherwise)
os.environ.setdefault("WORDMUTE_NO_UPDATE_CHECK", "1")
# bulk file adds probe synchronously in tests — a background probe
# thread living past its test crashes Qt teardown at session end
os.environ.setdefault("WORDMUTE_SYNC_PROBE", "1")


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
