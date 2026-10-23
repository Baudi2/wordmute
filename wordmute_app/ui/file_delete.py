"""Shared confirm-then-recycle flow for the queue and history menus."""

from ..core import cleanup, review
from .dialogs import confirm, inform
from .i18n import tr


def loses_review(files) -> bool:
    """The deletion takes a review sidecar but leaves its clean output:
    the result stays on disk, yet it can never be reviewed or rebuilt
    again (bringing a word back needs the original). A user deleted
    three sources right after processing and found «Проверка» dead on
    the two videos they had not reviewed yet."""
    names = {str(f) for f in files}
    return any(name.endswith(review.REVIEW_SUFFIX)
               and name[:-len(review.REVIEW_SUFFIX)] not in names
               for name in names)


def confirm_and_recycle(parent, files) -> bool:
    """Ask, then move to the Recycle Bin. Returns True if deleted."""
    if not files:
        return False
    names = [f.name for f in files[:8]]
    if len(files) > 8:
        names.append("…")
    body = tr("They can be restored from the Recycle Bin.")
    if loses_review(files):
        body = (tr("The review file goes too: after this the video can't "
                   "be reviewed or rebuilt — bringing a word back needs "
                   "the original. Review it first.") + "\n\n" + body)
    if not confirm(parent,
                   title=tr("Move {} file(s) to the Recycle Bin?")
                   .format(len(files)),
                   body=body, files=names, ok_text=tr("To Recycle Bin")):
        return False
    try:
        cleanup.send_to_recycle_bin(files)
        return True
    except OSError as exc:
        inform(parent, title=tr("Delete failed"), body=str(exc))
        return False
