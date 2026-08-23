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


LOG_NAME = "wordmute.log"
_log_handle = None


def _install_crash_log():
    """Every silent failure so far had nowhere to leave a trace: the
    windowed build sends stderr to devnull, so a Python exception in a
    slot, a worker that died, or Qt's own fatal message («QThread:
    Destroyed while thread is still running») vanished with the window.
    %APPDATA%\\WordMute\\wordmute.log collects: Python tracebacks from
    any thread (sys.excepthook + threading.excepthook), faulthandler
    dumps on a hard crash, Qt messages (see _install_qt_log) and
    whatever libraries print to stderr when there is no console."""
    global _log_handle
    import faulthandler
    import threading
    import traceback
    from datetime import datetime

    from . import __version__
    from .core import config
    try:
        path = config.data_dir() / LOG_NAME
        if path.exists() and path.stat().st_size > 2_000_000:
            path.replace(path.with_name(LOG_NAME + ".1"))   # one generation
        handle = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    _log_handle = handle
    handle.write(f"\n=== WordMute {__version__} · "
                 f"{datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    if sys.stderr is None:           # pythonw / frozen: no console
        sys.stderr = handle
    faulthandler.enable(file=handle, all_threads=True)

    def log_exception(exc_type, exc, tb):
        handle.write("".join(traceback.format_exception(exc_type, exc, tb)))
        handle.flush()

    def excepthook(exc_type, exc, tb):
        log_exception(exc_type, exc, tb)
        if sys.stderr is not handle:             # a console too
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook
    threading.excepthook = lambda args: log_exception(
        args.exc_type, args.exc_value, args.exc_traceback)
    return handle


def _install_qt_log():
    """Qt's warnings and fatals go to the same file (a fatal is the
    last line before the process dies — exactly the trace we lacked)."""
    if _log_handle is None:
        return
    from PySide6.QtCore import qInstallMessageHandler

    def handler(mode, context, message):
        _log_handle.write(f"[qt] {message}\n")
        _log_handle.flush()
        if sys.stderr is not _log_handle:
            print(message, file=sys.stderr)

    qInstallMessageHandler(handler)


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
    _install_crash_log()             # takes over a missing stderr
    if sys.stderr is None:           # log unavailable: still need a sink
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    _set_app_identity()
    _use_bundled_ffmpeg()
    # Xet lock-file paths contain characters illegal on Windows
    # (WinError 123); the engine sets this for itself, the setup and
    # Models-tab download subprocesses inherit it from here
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

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
    from .ui.i18n import set_language, tr
    from .ui.theme import app_icon, apply_theme

    settings = config.load_settings()
    set_language(settings.get("ui_language", "en"))

    _install_qt_log()
    app = QApplication(sys.argv)
    app.setApplicationName("WordMute")
    install_qt_translations(app, settings.get("ui_language", "en"))
    apply_theme(app, settings.get("theme", "dark"))
    app.setWindowIcon(app_icon())

    # one instance: a second window wrote ITS copy of settings.json
    # over this one's on close, and two first-run wizards raced on the
    # same runtime folder. The lock lives as long as main() does.
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(config.data_dir() / "wordmute.lock"))
    if not lock.tryLock(200):
        if not os.environ.get("WORDMUTE_SMOKE"):
            from .ui.dialogs import inform
            inform(None, title=tr("WordMute is already running."),
                   body=tr("Use the open window — a second copy would "
                           "overwrite its settings."))
        return 0

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
    code = app.exec()
    # workers that ignored their cancel within the close-time budget
    # (a model load, a stalled download, an ffmpeg pass) were detached
    # from the window so it could close; give them one more moment,
    # then leave without Qt's teardown — destroying a running QThread
    # aborts the process (0xC0000409). Settings and history are already
    # written by then.
    from .ui.threads import shutdown_detached
    if not shutdown_detached(10000):
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:
                pass
        os._exit(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
