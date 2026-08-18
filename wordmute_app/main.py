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


def qt_translation_dirs() -> list:
    """Where Qt's own .qm catalogs can live: the path Qt reports, plus
    the two places a PyInstaller bundle puts them."""
    from pathlib import Path

    from PySide6.QtCore import QLibraryInfo
    dirs = [Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs += [Path(base) / "PySide6" / "translations",
                 Path(base) / "PySide6" / "Qt" / "translations"]
    import PySide6
    dirs.append(Path(PySide6.__file__).parent / "translations")
    return dirs


def install_qt_translations(app, language: str):
    """Qt's built-in dialogs (QFileDialog, and any QMessageBox that
    survives) take their button labels from Qt's own catalog, not ours —
    without qtbase_<lang>.qm a Russian UI shows English «Yes/No/Open»."""
    from PySide6.QtCore import QTranslator
    code = (language or "en").split("_")[0]
    if code == "en":
        return None                     # Qt's source language
    for directory in qt_translation_dirs():
        translator = QTranslator(app)
        if translator.load(f"qtbase_{code}", str(directory)):
            app.installTranslator(translator)
            # keep a reference: a collected QTranslator stops translating
            app._qt_translator = translator
            return translator
    return None


APP_USER_MODEL_ID = "Baudi2.WordMute"


def _set_app_identity():
    """Windows attributes taskbar grouping and tray notifications to
    the process AppUserModelID — without this a dev run shows up as
    «Python». The installer registers the same ID on the Start-menu
    shortcut so notifications carry the WordMute name and icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID)
    except (OSError, AttributeError):
        pass


def main():
    # under pythonw / a frozen GUI there is no stdout; give print()ing
    # code (engine default reporter, libraries) a safe sink
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    _set_app_identity()
    _use_bundled_ffmpeg()

    # slim installer: engine packages + ffmpeg live in an app-managed
    # runtime downloaded on first run
    from .core import runtime_env
    runtime_env.activate()

    report = os.environ.get("WORDMUTE_RUNTIME_REPORT")
    if report:  # diagnostics/support mode: write status json and exit
        runtime_env.write_report(report)
        return 0

    # libraries (GigaAM/pyannote, yt-dlp) spawn their own ffmpeg/ffprobe;
    # without this each one flashes a console window under pythonw
    from .core.proc import install_global_no_window
    install_global_no_window()

    from PySide6.QtWidgets import QApplication

    from .core import config
    from .ui.i18n import set_language
    from .ui.theme import app_icon, apply_theme

    settings = config.load_settings()
    set_language(settings.get("ui_language", "en"))

    app = QApplication(sys.argv)
    app.setApplicationName("WordMute")
    install_qt_translations(app, settings.get("ui_language", "en"))
    apply_theme(app, settings.get("theme", "dark"))
    app.setWindowIcon(app_icon())

    if (getattr(sys, "frozen", False) and runtime_env.missing_required()
            and not os.environ.get("WORDMUTE_SMOKE")):
        from .ui.setup_dialog import SetupDialog
        setup = SetupDialog(first_run=True)
        if not setup.exec():
            return 0  # can't run without the required components
        runtime_env.activate()

    from .ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    if os.environ.get("WORDMUTE_SMOKE"):  # automated startup check
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
