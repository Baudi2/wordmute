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
