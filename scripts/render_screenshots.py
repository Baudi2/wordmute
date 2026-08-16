"""Render EVERY WordMute screen, tab, dialog and notable state with
staged demo data, for design round-trips.

Russian UI at 2x (RU strings run ~40% longer than EN — the worst case
for layout, and the app's main audience), dark theme for everything
plus a light-theme set of the main screens. A throwaway APPDATA and
fake paths keep real user data out of the shots.

    python scripts/render_screenshots.py           -> docs/design/*.png
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# native platform (not offscreen): offscreen lacks the system fonts and
# turns Cyrillic into tofu. 2x = crisp enough to design against.
_fake_appdata = tempfile.mkdtemp(prefix="wm_shots_appdata_")
os.environ["APPDATA"] = _fake_appdata
# an empty LOCALAPPDATA too: the wizard must render its clean-machine
# first-run state, not "already installed" on the dev box
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="wm_shots_local_")
os.environ["QT_SCALE_FACTOR"] = "2"
os.environ["WORDMUTE_NO_UPDATE_CHECK"] = "1"
os.environ["WORDMUTE_SYNC_PROBE"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path(__file__).resolve().parent.parent / "docs" / "design"
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()
WORK = Path(tempfile.mkdtemp(prefix="wm_shots_"))

from PySide6.QtCore import QCoreApplication, QEvent, QPoint
from PySide6.QtWidgets import QApplication, QMessageBox

from wordmute_app.core import gpu, history, models, review
from wordmute_app.core.jobs import QueueItem
from wordmute_app.ui.i18n import set_language
from wordmute_app.ui.theme import apply_theme

app = QApplication(sys.argv)
set_language("ru")
apply_theme(app, "dark")
# a typical target machine, so GPU-dependent copy shows its normal state
gpu.detect_gpus = lambda: [gpu.GpuInfo("NVIDIA GeForce RTX 4060", 8188)]

_index = 0


def shot(widget, name, hide=True):
    """Item widgets (queue cards) need a real layout pass before grab."""
    global _index
    widget.show()
    for _ in range(4):
        app.processEvents()
        # processEvents skips DeferredDelete: without this, widgets a
        # rebuild replaced (table cell buttons) stay painted on top
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    pixmap = widget.grab()
    if hide:
        widget.hide()
    path = OUT / f"{_index:02d}_{name}.png"
    pixmap.save(str(path), "PNG")
    print(f"{path.name:34} {pixmap.width()}x{pixmap.height()}")
    _index += 1


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


# ---------------------------------------------------------- staged data
# real files, so the History "files on disk" glyph shows ● / ◐ / ○
def staged_file(name: str) -> Path:
    path = WORK / name
    path.write_bytes(b"x")
    return path


records = [
    {"name": "Лекция_01.mp4", "status": "ok", "muted": 12,
     "source": str(staged_file("Лекция_01.mp4")),
     "output": str(staged_file("Лекция_01.clean.mp4")),
     "plan": "gigaam(v3_rnnt) -> gigaam(v3_rnnt) -> whisper(large-v3)",
     "stage_seconds": {"passes": [{"engine": "gigaam", "seconds": 74},
                                  {"engine": "gigaam", "cached": True},
                                  {"engine": "whisper", "seconds": 131}],
                       "mute": 41, "total": 254}},
    {"name": "Разбор фильма — часть 2", "status": "ok", "muted": 22,
     "source": str(WORK / "Разбор.mp4"),                 # source deleted
     "output": str(staged_file("Разбор.clean.mp4")),
     "plan": "whisper(large-v3)", "downloaded_bytes": 1_820_000_000,
     "stage_seconds": {"download": 372, "mute": 28, "total": 690,
                       "passes": [{"engine": "whisper", "seconds": 289}]}},
    {"name": "How to Maintain your First Car", "status": "ok", "muted": 5,
     "source": str(WORK / "car.mp4"), "output": str(WORK / "car.clean.mp4"),
     "plan": "whisper(large-v3)", "downloaded_bytes": 640_000_000,
     "stage_seconds": {"download": 141, "mute": 12, "total": 402,
                       "passes": [{"engine": "whisper", "seconds": 249}]}},
    {"name": "Интервью.mkv", "status": "error", "muted": 0,
     "error": "ffmpeg failed (code 1)", "plan": "gigaam(v3_rnnt)",
     "source": str(staged_file("Интервью.mkv")), "output": ""},
    {"name": "Подкаст_44.mp3", "status": "ok", "muted": 3,
     "source": str(staged_file("Подкаст_44.mp3")),
     "output": str(staged_file("Подкаст_44.clean.mp3")),
     "plan": "whisper(large-v3)"},
]
for record in records:
    history.append_history(record)

models.whisper_model_status = lambda: [
    {"model": "large-v3", "repo": "Systran/faster-whisper-large-v3",
     "downloaded": True, "size_bytes": 3_090_000_000},
    {"model": "large-v3-turbo",
     "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
     "downloaded": True, "size_bytes": 1_620_000_000},
    {"model": "medium", "repo": "Systran/faster-whisper-medium",
     "downloaded": False, "size_bytes": 0},
    {"model": "small", "repo": "Systran/faster-whisper-small",
     "downloaded": False, "size_bytes": 0},
    {"model": "base", "repo": "Systran/faster-whisper-base",
     "downloaded": False, "size_bytes": 0},
]
models.gigaam_cache_dirs = lambda: [(WORK / "gigaam-v3-onnx", 892_000_000)]

thumb_a, thumb_b, thumb_c = WORK / "a.jpg", WORK / "b.jpg", WORK / "c.jpg"
ffmpeg("-f", "lavfi", "-i",
       "gradients=size=192x108:duration=0.1:c0=0x9184d9:c1=0x1b2440",
       "-frames:v", "1", str(thumb_a))
ffmpeg("-f", "lavfi", "-i", "testsrc2=size=192x108:duration=0.1",
       "-frames:v", "1", str(thumb_b))
ffmpeg("-f", "lavfi", "-i",
       "gradients=size=192x108:duration=0.1:c0=0x2f8f6b:c1=0x101820",
       "-frames:v", "1", str(thumb_c))

# ------------------------------------------------------------ main window
from wordmute_app.ui.main_window import MainWindow

win = MainWindow()
win.resize(1100, 760)
shot(win, "queue_empty", hide=False)

rows = [
    (QueueItem(kind="file", path=Path(r"D:\Видео\Лекция_01.mp4"),
               duration=5415), "готово"),
    (QueueItem(kind="url", url="https://rutube.ru/video/a1b2c3/",
               title="Разбор фильма — часть 2", format_label="1080p mp4",
               duration=2710, lang_profile="ru"), "обработка"),
    (QueueItem(kind="url", url="https://www.youtube.com/watch?v=xyzXYZ01",
               title="How to Maintain your First Car",
               format_label="до 1080p", duration=1180,
               lang_profile="en"), "скачивание"),
    (QueueItem(kind="file", path=Path(r"D:\Видео\Подкаст_44.mp3"),
               duration=7300), "в очереди"),
]
for item, status in rows:
    win._insert_row(item, status=status)
win._card(0).set_thumb(thumb_a)
win._card(0).set_status("готово → Лекция_01.clean.mp4", state="ok")
win._card(0).set_actions(review=True, open_=True)
win._card(1).set_thumb(thumb_b)
win._card(1).set_status(
    "проход 1/3 · распознавание 62 % · осталось ~4 мин 10 с", progress=0.62)
win._card(2).set_thumb(thumb_c)
win._card(2).set_status("скачивание 41 % · 2,3 МБ/с", progress=0.41)
win.progress_bar.setRange(0, 400)
win.progress_bar.setValue(155)
win.percent_label.setText("38%")
win.status_label.setText("Распознавание… обработано 32 мин 10 с аудио")
for line in [
    "Списки слов: 6110 записей. План: gigaam(v3_rnnt) -> gigaam(v3_rnnt)"
    " -> whisper(large-v3).",
    "=== Лекция_01.mp4 ===",
    "— проход 1/3 (gigaam) —",
    "[model] loading GigaAM v3_rnnt (onnx) ...",
    "14231 слов в расшифровке",
    "12 интервал(ов) для заглушения:",
    "    00:03:12.480 - 00:03:12.930   бог",
    "    00:14:41.200 - 00:14:41.760   чудом",
    "Заглушение 12 сегмент(ов) через ffmpeg...",
    "Результат -> D:\\Видео\\Лекция_01.clean.mp4",
]:
    win._append_log(line)
shot(win, "queue_running", hide=False)

win.log_toggle.setChecked(True)
shot(win, "queue_log_open", hide=False)
win.log_toggle.setChecked(False)

win._toggle_setup_panel()          # pass plan + word list options
shot(win, "queue_setup_panel", hide=False)
win._toggle_setup_panel()

# the per-card ⋯ menu (language profile, delete files): built, not
# exec()ed — exec would block on a modal popup
card_menu, _ = win._build_card_menu(0)
for action in card_menu.actions():
    action.setEnabled(True)          # staged paths don't exist on disk
card_menu.popup(QPoint(0, 0))
for _ in range(3):
    app.processEvents()
shot(card_menu, "queue_card_menu")
# never fetch it via action.menu(): PySide hands ownership to the
# discarded temporary and deletes the C++ submenu
lang_menu = card_menu._lang_menu
lang_menu.popup(QPoint(0, 0))
for _ in range(3):
    app.processEvents()
shot(lang_menu, "queue_card_menu_language")
lang_menu.close()
card_menu.close()

for name, tab in (("wordlists", win.wordlists_tab),
                  ("transcript", win.transcript_tab),
                  ("models", win.models_tab),
                  ("history", win.history_tab),
                  ("settings", win.settings_tab)):
    win.tabs.setCurrentWidget(tab)
    if name == "wordlists":
        tab.tester_input.setText("колдовать и демонстрация")
    if name == "transcript":
        media = WORK / "Лекция_01.mp4"
        words, position = [], 0.0
        for word in ("сегодня мы поговорим о том как устроена память "
                     "человека и почему мы забываем важные вещи а "
                     "помним всякую ерунду").split():
            words.append({"w": word, "s": round(position, 2),
                          "e": round(position + 0.4, 2)})
            position += 0.55
        (WORK / "Лекция_01.mp4.words.json").write_text(
            json.dumps(words, ensure_ascii=False), encoding="utf-8")
        tab.load_media(media)
    if name == "models":
        tab._runtime_bytes = 2_410_000_000
        tab.refresh()
    if name == "history":
        tab.refresh()
    if name == "settings":
        tab.cookies_edit.setText(r"C:\Видео\boosty_cookies.txt")
        tab.download_dir_edit.setText(r"D:\Видео\Загрузки")
    shot(win, f"tab_{name}", hide=False)

win.tabs.setCurrentIndex(0)

# ------------------------------------------------------------ dialogs
from wordmute_app.ui.url_dialog import AddUrlDialog

url = AddUrlDialog(url="https://rutube.ru/video/a1b2c3/", auto_fetch=False)
url.resize(820, 560)
url._on_formats_ready({
    "title": "Разбор фильма — часть 2", "duration": 2710,
    "url": "https://rutube.ru/video/a1b2c3/",
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
shot(url, "dialog_add_url_single")

batch = AddUrlDialog(auto_fetch=False)
batch.resize(820, 560)
batch.url_edit.setPlainText(
    "https://rutube.ru/video/a1b2c3/\n"
    "https://rutube.ru/video/d4e5f6/\n"
    "https://www.youtube.com/watch?v=xyzXYZ01\n"
    "https://vkvideo.ru/video-12345_678")
shot(batch, "dialog_add_url_batch")

# review dialog, with a real waveform strip
src = WORK / "Лекция_01_src.wav"
ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=8",
       "-ar", "16000", str(src))
out = WORK / "Лекция_01.clean.mp4"
review_path = review.save_review(src, out, 100, [
    {"s": 2.48, "e": 3.10, "text": "чудеса", "pass": 1,
     "engine": "gigaam", "muted": True},
    {"s": 3.78, "e": 4.44, "text": "обожаю", "pass": 1,
     "engine": "gigaam", "muted": False},
    {"s": 5.10, "e": 5.60, "text": "бог", "pass": 2,
     "engine": "whisper", "muted": True},
    {"s": 6.20, "e": 6.75, "text": "верю", "pass": 3,
     "engine": "whisper", "muted": True},
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
rev = rd.ReviewDialog(review_path)
rev.resize(900, 640)
rev.show()
for _ in range(4):
    app.processEvents()
rev.table.selectRow(0)
deadline = time.monotonic() + 20            # let the peaks worker finish
while rev._wave_worker is not None and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.05)
for _ in range(4):
    app.processEvents()
shot(rev, "dialog_review")

# the "move files to the Recycle Bin" confirmation
from wordmute_app.ui import file_delete

_asked = {}


def _capture_question(parent, title, text, *a, **kw):
    _asked["title"], _asked["text"] = title, text
    return QMessageBox.StandardButton.No


_real_question = QMessageBox.question
QMessageBox.question = staticmethod(_capture_question)
file_delete.confirm_and_recycle(
    win, [WORK / "Лекция_01.mp4", WORK / "Лекция_01.mp4.words.json",
          WORK / "Лекция_01.clean.mp4.wordmute.json"])
QMessageBox.question = _real_question
box = QMessageBox(QMessageBox.Question, _asked.get("title", "WordMute"),
                  _asked.get("text", ""),
                  QMessageBox.Yes | QMessageBox.No, win)
shot(box, "dialog_delete_files")

# ------------------------------------------------------------ setup wizard
from wordmute_app.ui.setup_dialog import STEP_KEYS, SetupDialog

wizard = SetupDialog(first_run=True)
wizard.show()
for _ in range(4):
    app.processEvents()
for index, key in enumerate(STEP_KEYS):
    if key == "install":
        wizard._refresh_install_rows()
        wizard._set_row_state("python", "done", "готово")
        wizard._set_row_state("ffmpeg", "done", "готово")
        wizard._set_row_state("whisper", "run", "скачивание… 63%")
        wizard.install_percent.setText("41%")
        wizard.total_progress.setRange(0, 100)
        wizard.total_progress.setValue(41)
        wizard.log_toggle.setChecked(True)
        for line in ["wordmute setup",
                     "  → python-3.12.10-embed-amd64.zip",
                     "  ✓ python runtime ready · get-pip ok",
                     "  → ffmpeg-release-essentials.zip (80 МБ)",
                     "  ✓ ffmpeg ready",
                     "  → faster-whisper, nvidia-cublas-cu12, "
                     "nvidia-cudnn-cu12 …"]:
            wizard.log.appendPlainText(line)
    wizard.set_step(index)
    for _ in range(3):
        app.processEvents()
    shot(wizard, f"wizard_{index}_{key}", hide=False)
wizard.hide()

# ------------------------------------------------------------ toast
try:
    from wordmute_app.ui.toasts import show_toast

    win.show()
    show_toast(win, "WordMute", "Готово: 3 файла · заглушено 37 слов")
    for _ in range(40):              # let the slide-in animation settle
        app.processEvents()
        time.sleep(0.03)
    toasts = [w for w in app.topLevelWidgets()
              if type(w).__name__ == "Toast" and w.isVisible()]
    if toasts:
        shot(toasts[0], "toast_finished")
except Exception as exc:                                  # noqa: BLE001
    print("toast skipped:", exc)

# ------------------------------------------------------------ light theme
apply_theme(app, "light")
win.tabs.setCurrentIndex(0)
shot(win, "light_queue", hide=False)
win.tabs.setCurrentWidget(win.settings_tab)
shot(win, "light_settings", hide=False)
win.tabs.setCurrentWidget(win.history_tab)
shot(win, "light_history", hide=False)
win.hide()

light_wizard = SetupDialog(first_run=True)
light_wizard.show()
for _ in range(3):
    app.processEvents()
light_wizard.set_step(2)
shot(light_wizard, "light_wizard_whisper")

print("\ndone ->", OUT)
sys.stdout.flush()
# staged widgets (toast timers, waveform threads) sometimes fault
# during interpreter teardown — the PNGs are already written
os._exit(0)
