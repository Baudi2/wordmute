"""Nocturne-styled in-app toasts (pyqttoast, MIT).

Always parent toasts to the MAIN window — never to the non-modal
review dialog (upstream pyqttoast issue #34 crashes on close there).
Complements the tray balloon: the balloon covers "window in the
background", toasts cover "user is looking at the app"."""

import os

os.environ.setdefault("QT_API", "pyside6")   # qtpy binding, pre-import

from pyqttoast import Toast, ToastPosition  # noqa: E402

from ..core import config  # noqa: E402

_DARK = {"bg": "#232532", "text": "#e9e9ed", "muted": "#9096a0",
         "accent": "#9184d9"}
_LIGHT = {"bg": "#f3f5fe", "text": "#292b31", "muted": "#5c5f6a",
          "accent": "#5d5294"}


def show_toast(parent, title: str, text: str = "",
               duration_ms: int = 4500) -> None:
    """Fire-and-forget; Toast instances are single-show by design."""
    from PySide6.QtGui import QColor, QFont

    # nothing to float over: pyqttoast deletes a toast whose parent is
    # not shown, and the next call into it raises «already deleted»
    if parent is not None and not parent.isVisible():
        return
    palette = (_DARK if config.load_settings().get("theme", "dark")
               == "dark" else _LIGHT)
    Toast.setPosition(ToastPosition.BOTTOM_RIGHT)
    Toast.setMaximumOnScreen(3)
    toast = Toast(parent)
    toast.setDuration(duration_ms)
    toast.setTitle(title)
    if text:
        toast.setText(text)
    toast.setShowIcon(False)
    # pyqttoast measures the label widths with the fonts set here and
    # then fixes their size — they must be the font the QSS actually
    # renders with (Inter 13px), or long Russian lines get cut off
    text_font = QFont()
    text_font.setFamilies(["Inter", "Segoe UI", "sans-serif"])
    text_font.setPixelSize(13)
    title_font = QFont(text_font)
    title_font.setBold(True)
    toast.setTitleFont(title_font)
    toast.setTextFont(text_font)
    toast.setBorderRadius(8)
    toast.setBackgroundColor(QColor(palette["bg"]))
    toast.setTitleColor(QColor(palette["text"]))
    toast.setTextColor(QColor(palette["muted"]))
    toast.setDurationBarColor(QColor(palette["accent"]))
    toast.setCloseButtonIconColor(QColor(palette["muted"]))
    toast.show()
