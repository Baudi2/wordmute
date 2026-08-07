"""Application entry point: python -m wordmute_app"""

import os
import sys


def _use_bundled_ffmpeg():
    """A frozen install ships ffmpeg/ffprobe in an ffmpeg/ subfolder;
    put it first on PATH so the app works without a system install."""
    if not getattr(sys, "frozen", False):
        return
    from pathlib import Path
    base = Path(sys.executable).parent
    for cand in (base / "ffmpeg", base / "ffmpeg" / "bin"):
        if (cand / "ffmpeg.exe").exists():
            os.environ["PATH"] = (str(cand) + os.pathsep
                                  + os.environ.get("PATH", ""))
            break


def main():
    # under pythonw / a frozen GUI there is no stdout; give print()ing
    # code (engine default reporter, libraries) a safe sink
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    _use_bundled_ffmpeg()

    from PySide6.QtWidgets import QApplication

    from .core import config
    from .ui.i18n import set_language
    from .ui.theme import app_icon, apply_theme

    settings = config.load_settings()
    set_language(settings.get("ui_language", "en"))

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("WordMute")
    apply_theme(app, settings.get("theme", "dark"))
    app.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    if os.environ.get("WORDMUTE_SMOKE"):  # automated startup check
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
