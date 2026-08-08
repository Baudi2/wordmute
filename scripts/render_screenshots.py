"""Render every WordMute screen (tabbed layout) with staged demo data
and save PNGs into docs/design/. Uses a throwaway APPDATA and fake
paths so no real user data appears in the screenshots."""

import json
import os
import sys
import tempfile
from pathlib import Path

# native platform (not offscreen): offscreen mode lacks the system
# fonts, turning Cyrillic into squares. Widgets are grabbed without
# show(), so nothing flashes on screen.
_fake_appdata = tempfile.mkdtemp(prefix="wm_shots_appdata_")
os.environ["APPDATA"] = _fake_appdata

sys.path.insert(0, r"C:\wordmute-app")

OUT = Path(r"C:\wordmute-app\docs\design")
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()
WORK = Path(tempfile.mkdtemp(prefix="wm_shots_"))

from PySide6.QtWidgets import QApplication

from wordmute_app.ui.theme import apply_theme

app = QApplication(sys.argv)
apply_theme(app, "dark")


def shot(widget, name):
    # item widgets (queue cards) need a real layout pass before grab
    widget.show()
    for _ in range(3):
        app.processEvents()
    pm = widget.grab()
    widget.hide()
    pm.save(str(OUT / f"{name}.png"), "PNG")
    print(name, pm.width(), "x", pm.height())


# staged history (shown in the History tab)
from wordmute_app.core import history

for rec in [
    {"name": "Лекция_01.mp4", "status": "ok", "muted": 12,
     "plan": "whisper(large-v3) -> whisper(large-v3)",
     "output": r"D:\Видео\Лекция_01.clean.mp4"},
    {"name": "Интервью.mkv", "status": "error",
     "error": "ffmpeg failed (code 1)", "muted": 0,
     "plan": "gigaam(v3_e2e_rnnt)", "output": ""},
    {"name": "Подкаст_44.mp3", "status": "ok", "muted": 3,
     "plan": "whisper(large-v3)", "output": r"D:\Видео\Подкаст_44.clean.mp3"},
]:
    history.append_history(rec)

# ---------------------------------------------------------------- window
from wordmute_app.core.jobs import QueueItem
from wordmute_app.ui.main_window import MainWindow

w = MainWindow()
w.resize(1100, 760)
shot(w, "00_queue_empty")
demo_rows = [
    (QueueItem(kind="file", path=Path(r"D:\Видео\Лекция_01.mp4"),
               duration=5415), "done → Лекция_01.clean.mp4 — "
                               "double-click to review"),
    (QueueItem(kind="file", path=Path(r"D:\Видео\Интервью.mkv"),
               duration=3122), "pass 1/2 · transcribing 62% · "
                               "~4 min 10 s left"),
    (QueueItem(kind="url", url="https://boosty.to/example/posts/demo",
               title="Разбор фильма — часть 2", format_label="1080p mp4",
               duration=2710), "queued (1080p mp4)"),
    (QueueItem(kind="file", path=Path(r"D:\Видео\Подкаст_44.mp3"),
               duration=7300), "queued"),
]
for item, status in demo_rows:
    w._insert_row(item, status=status)

# demo thumbnails via ffmpeg test patterns
import subprocess

thumb1 = WORK / "t1.jpg"
thumb2 = WORK / "t2.jpg"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                "-i", "testsrc2=size=192x108:duration=0.1",
                "-frames:v", "1", str(thumb1)], check=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                "-i", "gradients=size=192x108:duration=0.1",
                "-frames:v", "1", str(thumb2)], check=True)
w._card(0).set_thumb(thumb1)
w._card(0).set_status("done → Лекция_01.clean.mp4", state="ok")
w._card(0).set_actions(review=True, open_=True)
w._card(1).set_thumb(thumb2)
w._card(1).set_status("pass 1/2 · transcribing 62% · ~4 min 10 s left",
                      progress=0.62)
w.progress_bar.setRange(0, 400)
w.progress_bar.setValue(155)
w.status_label.setText("Transcribing… 32 min 10 s of audio processed")
for line in [
    "Word list: 6110 entries. Plan: whisper(large-v3) -> whisper(large-v3).",
    "=== Лекция_01.mp4 ===",
    "Transcribing Лекция_01.mp4 with whisper (first run is the slow part)...",
    "14231 words in transcript",
    "12 interval(s) to mute:",
    "    00:03:12.480 - 00:03:12.930   бог",
    "    00:14:41.200 - 00:14:41.760   чудом",
    "Muting 12 segment(s) with ffmpeg...",
    "Output -> D:\\Видео\\Лекция_01.clean.mp4",
    "Review data -> D:\\Видео\\Лекция_01.clean.mp4.wordmute.json",
]:
    w._append_log(line)
w.log_toggle.setChecked(True)
w.tabs.setTabText(0, "Queue · 38%")
w.percent_label.setText("38%")
shot(w, "01_queue_tab")

# word lists tab (template lists were copied into the fake APPDATA)
w.tabs.setCurrentWidget(w.wordlists_tab)
w.wordlists_tab.tester_input.setText("колдовать и демонстрация")
shot(w, "02_wordlists_tab")

# transcript tab with a demo cache
media = WORK / "Лекция_01.mp4"
words = []
texts = ("сегодня мы поговорим о том как устроена память человека "
         "и почему мы забываем важные вещи а помним ерунду").split()
tpos = 0.0
for word in texts:
    words.append({"w": word, "s": round(tpos, 2), "e": round(tpos + 0.4, 2)})
    tpos += 0.55
(WORK / "Лекция_01.mp4.words.json").write_text(
    json.dumps(words, ensure_ascii=False), encoding="utf-8")
w.tabs.setCurrentWidget(w.transcript_tab)
w.transcript_tab.load_media(media)
shot(w, "03_transcript_tab")

w.tabs.setCurrentWidget(w.models_tab)
w.models_tab.refresh()
shot(w, "04_models_tab")

w.tabs.setCurrentWidget(w.history_tab)
w.history_tab.refresh()
shot(w, "05_history_tab")

w.tabs.setCurrentWidget(w.settings_tab)
w.settings_tab.cookies_edit.setText(r"C:\Видео\boosty_cookies.txt")
w.settings_tab.download_dir_edit.setText(r"D:\Видео\Загрузки")
shot(w, "06_settings_tab")

# ---------------------------------------------------------------- dialogs
from wordmute_app.ui.url_dialog import AddUrlDialog

u = AddUrlDialog(url="https://boosty.to/example/posts/demo")
u._on_formats_ready({
    "title": "Разбор фильма — часть 2", "duration": 2710,
    "url": "https://boosty.to/example/posts/demo",
    "formats": [
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1",
         "acodec": "none", "height": 1080, "fps": 25,
         "filesize": 620 * 1024 ** 2, "format_note": "1080p"},
        {"format_id": "22", "ext": "mp4", "vcodec": "avc1",
         "acodec": "mp4a", "height": 720, "fps": 25,
         "filesize_approx": 380 * 1024 ** 2, "format_note": "720p"},
        {"format_id": "18", "ext": "mp4", "vcodec": "avc1",
         "acodec": "mp4a", "height": 360, "fps": 25,
         "filesize": 120 * 1024 ** 2, "format_note": "360p"},
        {"format_id": "140", "ext": "m4a", "vcodec": "none",
         "acodec": "mp4a", "tbr": 129, "format_note": "audio"},
    ],
})
shot(u, "07_add_url")

from wordmute_app.core import review
from wordmute_app.ui import review_dialog as rd


class _NoPlayer:
    def play(self, *a):
        pass

    def stop(self):
        pass

    def dispose(self):
        pass


rd.SnippetPlayer = _NoPlayer
src = WORK / "Лекция_01_src.mp4"
src.write_bytes(b"x")
outp = WORK / "Лекция_01.clean.mp4"
outp.write_bytes(b"x")
rp = review.save_review(src, outp, 100, [
    {"s": 192.48, "e": 192.93, "text": "бог", "pass": 1,
     "engine": "whisper", "muted": True},
    {"s": 881.2, "e": 881.76, "text": "чудом", "pass": 1,
     "engine": "whisper", "muted": True},
    {"s": 1204.1, "e": 1204.9, "text": "обожаю", "pass": 1,
     "engine": "whisper", "muted": False},
    {"s": 2411.0, "e": 2411.6, "text": "верю", "pass": 2,
     "engine": "gigaam", "muted": True},
])
r = rd.ReviewDialog(rp)
shot(r, "08_review")

from wordmute_app.engine import wordmute as engine

engine.discover_ffmpeg_shared_dir = lambda: r"C:\ffmpeg-shared\bin"
from wordmute_app.ui.gigaam_wizard import GigaamWizard

g = GigaamWizard()
shot(g, "09_gigaam_wizard")

# light theme sample
apply_theme(app, "light")
w.tabs.setCurrentIndex(0)
shot(w, "10_queue_light")

# russian interface sample (dark)
apply_theme(app, "dark")
from wordmute_app.ui.i18n import set_language

set_language("ru")
w_ru = MainWindow()
w_ru.resize(1100, 760)
shot(w_ru, "11_queue_ru")
set_language("en")

print("done ->", OUT)
