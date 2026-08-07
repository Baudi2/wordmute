"""Application entry point: python -m wordmute_app"""

import sys


def main():
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
