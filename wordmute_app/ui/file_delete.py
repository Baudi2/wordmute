"""Shared confirm-then-recycle flow for the queue and history menus."""

from ..core import cleanup
from .dialogs import confirm, inform
from .i18n import tr


def confirm_and_recycle(parent, files) -> bool:
    """Ask, then move to the Recycle Bin. Returns True if deleted."""
    if not files:
        return False
    names = [f.name for f in files[:8]]
    if len(files) > 8:
        names.append("…")
    if not confirm(parent,
                   title=tr("Move {} file(s) to the Recycle Bin?")
                   .format(len(files)),
                   body=tr("They can be restored from the Recycle Bin."),
                   files=names, ok_text=tr("To Recycle Bin")):
        return False
    try:
        cleanup.send_to_recycle_bin(files)
        return True
    except OSError as exc:
        inform(parent, title=tr("Delete failed"), body=str(exc))
        return False
