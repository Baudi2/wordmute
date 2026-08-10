"""Shared confirm-then-recycle flow for the queue and history menus."""

from PySide6.QtWidgets import QMessageBox

from ..core import cleanup
from .i18n import tr


def confirm_and_recycle(parent, files) -> bool:
    """Ask, then move to the Recycle Bin. Returns True if deleted."""
    if not files:
        return False
    names = "\n".join(f.name for f in files[:8])
    if len(files) > 8:
        names += "\n…"
    question = (tr("Move {} file(s) to the Recycle Bin?").format(len(files))
                + "\n\n" + names)
    if QMessageBox.question(parent, "WordMute", question) \
            != QMessageBox.StandardButton.Yes:
        return False
    try:
        cleanup.send_to_recycle_bin(files)
        return True
    except OSError as exc:
        QMessageBox.warning(parent, "WordMute",
                            tr("Delete failed: {}").format(exc))
        return False
