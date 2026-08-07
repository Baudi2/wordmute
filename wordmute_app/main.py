"""Application entry point: python -m wordmute_app"""

import os
import sys


def main():
    # under pythonw / a frozen GUI there is no stdout; give print()ing
    # code (engine default reporter, libraries) a safe sink
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    from PySide6.QtWidgets import QApplication

    from .core import config
    from .ui.i18n import set_language

    set_language(config.load_settings().get("ui_language", "en"))

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("WordMute")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
