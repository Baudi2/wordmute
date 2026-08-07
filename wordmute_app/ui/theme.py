"""Theme loading: the Nocturne QSS files from the design handoff.

apply_theme() sets the Fusion base style (predictable QSS rendering),
loads the requested stylesheet with icon urls rewritten to absolute
paths, and fixes the placeholder-text palette color the QSS cannot
reach. Safe to call again at runtime to switch themes live."""

import re

from PySide6.QtGui import QColor, QIcon, QPalette

from ..core.config import resources_dir

THEMES = {
    "dark": "wordmute.qss",
    "light": "wordmute-light.qss",
}
DEFAULT_THEME = "dark"

_PLACEHOLDER = {"dark": "#75798c", "light": "#8b8fa3"}


def theme_dir():
    return resources_dir() / "theme"


def load_stylesheet(name: str) -> str:
    name = name if name in THEMES else DEFAULT_THEME
    path = theme_dir() / THEMES[name]
    qss = path.read_text(encoding="utf-8")
    # icon urls in the QSS are relative to the file; Qt resolves url()
    # against the process cwd, so rewrite to absolute (forward slashes)
    base = theme_dir().as_posix()
    return re.sub(r"url\((icons/[^)]+)\)", rf"url({base}/\1)", qss)


def apply_theme(app, name: str) -> None:
    name = name if name in THEMES else DEFAULT_THEME
    app.setStyle("Fusion")
    app.setStyleSheet(load_stylesheet(name))
    palette = app.palette()
    palette.setColor(QPalette.PlaceholderText, QColor(_PLACEHOLDER[name]))
    app.setPalette(palette)


def app_icon() -> QIcon:
    return QIcon(str(theme_dir() / "wordmute-icon.svg"))
