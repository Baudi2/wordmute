"""Material for the brag video (scripts/brag_video/render.py). Two
renders of the real Review window: all four
words muted, then «обожаю» un-muted by a click. Staged data only, a
staged source path in the header (never a real one). 2x, offscreen."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "brag-output" / "work"        # gitignored working folder
WORK.mkdir(parents=True, exist_ok=True)
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="wm_brag_appdata_")
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="wm_brag_local_")
os.environ["QT_SCALE_FACTOR"] = "2"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["WORDMUTE_NO_UPDATE_CHECK"] = "1"
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QLabel

from wordmute_app.core import review
from wordmute_app.ui.i18n import set_language, tr
from wordmute_app.ui.theme import apply_theme

app = QApplication(sys.argv)
set_language("ru")
apply_theme(app, "dark")

stage = Path(tempfile.mkdtemp(prefix="wm_brag_stage_"))
src = stage / "Лекция_01.mp4"            # a real file: the waveform needs peaks
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "sine=frequency=220:duration=8:sample_rate=16000",
                "-af", "tremolo=f=3:d=0.9", str(src.with_suffix(".wav"))],
               check=True)
src.with_suffix(".wav").rename(src)
out = stage / "Лекция_01.clean.mp4"
sidecar = review.save_review(src, out, 100, [
    {"s": 2.48, "e": 3.10, "text": "чудеса", "pass": 1, "engine": "gigaam",
     "muted": True},
    {"s": 3.78, "e": 4.44, "text": "обожаю", "pass": 1, "engine": "gigaam",
     "muted": True},
    {"s": 5.10, "e": 5.60, "text": "бог", "pass": 2, "engine": "whisper",
     "muted": True},
    {"s": 6.20, "e": 6.75, "text": "верю", "pass": 3, "engine": "whisper",
     "muted": True},
])

from wordmute_app.ui import review_dialog as rd


class _NoPlayer:
    def play(self, *a):
        pass

    def stop(self):
        pass

    def dispose(self):
        pass


rd.SnippetPlayer = _NoPlayer
dialog = rd.ReviewDialog(sidecar)
dialog.resize(900, 470)
dialog.show()
for label in dialog.findChildren(QLabel):
    if label.objectName() == "review_summary":
        label.setText("<b>Лекция_01.clean.mp4</b><br>"
                      f"{tr('Source')}: D:\\Видео\\Лекция_01.mp4")
for _ in range(4):
    app.processEvents()
dialog.table.selectRow(1)           # the strip is built for the selected row
deadline = time.monotonic() + 20
while dialog._wave_worker is not None and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.05)


def grab(name):
    for _ in range(6):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    pixmap = dialog.grab()
    pixmap.save(str(WORK / name), "PNG")
    print(name, pixmap.width(), "x", pixmap.height())


grab("review_a.png")
dialog.table.item(1, rd.COL_MUTE).setCheckState(Qt.Unchecked)
grab("review_b.png")
# where the row-2 checkbox sits, in the grab's pixels (for the cursor)
rect = dialog.table.visualItemRect(dialog.table.item(1, rd.COL_MUTE))
point = dialog.table.viewport().mapTo(dialog, rect.center())
import json
import shutil
json.dump({"checkbox": [point.x() * 2, point.y() * 2]},
          open(WORK / "review_meta.json", "w"))
# the other UI material: the design renders (scripts/render_screenshots.py)
for target, render in (("queue.png", "02_queue_running.png"),
                       ("addurl.png", "16_dialog_add_url_single.png"),
                       ("toast.png", "28_toast_finished.png")):
    shutil.copy2(ROOT / "docs" / "design" / render, WORK / target)
print("checkbox center at 2x:", point.x() * 2, point.y() * 2)
sys.stdout.flush()
os._exit(0)
