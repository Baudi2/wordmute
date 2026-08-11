import os

import pytest

# tests must never hit the network: the startup self-update check is
# disabled globally (it spawns a delayed worker thread otherwise)
os.environ.setdefault("WORDMUTE_NO_UPDATE_CHECK", "1")


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
