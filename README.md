# WordMute App

Windows desktop app for muting unwanted words/phrases in video and audio.
Transcribes locally (faster-whisper or GigaAM), matches against a
user-editable word list, and mutes the matched moments with ffmpeg —
video stream copied untouched. Runs fully offline once models are
downloaded.

Built around the proven `wordmute` CLI engine, which lives vendored in
`wordmute_app/engine/` — its matching, muting, and caching logic is the
source of truth and must not be re-implemented in app layers.

## Layout

```
wordmute_app/
  engine/       vendored engine (wordmute.py + wordlist tidy logic)
  core/         Qt-free app logic: queue, yt-dlp, config, GPU/HF setup
  ui/           PySide6 GUI (QThread workers, i18n)
  resources/    word-list templates shipped with the app (RU + EN);
                copied to the user's data dir on first run — users edit
                their copies, never these
packaging/      PyInstaller spec + Inno Setup script
tests/          engine parity + regression tests (python -m pytest tests)
```

## Engine changes vs. the original CLI

Three portability changes only — behavior is otherwise identical and
covered by parity tests (`tests/test_parity_with_cli.py`):

1. FFmpeg shared-build DLL directory is discovered dynamically
   (winget locations, then PATH) instead of a hardcoded path;
   `configure_ffmpeg_shared_dir()` lets the app/installer override.
2. Console output goes through a swappable reporter
   (`set_reporter(fn)`) emitting structured events, so the GUI can show
   progress; the default reporter reproduces the original CLI output.
3. `HF_HUB_DISABLE_XET=1` is set automatically before GigaAM loads
   (Windows lock-file path bug, WinError 123).

## Word lists

The shipped lists are a curated starting template (extensive
religious/mystical/occult vocabulary). Entry types are deliberate:

```
слово          exact match (case-insensitive, ё=е)
корень*        stem — word starts with this
*корень*       substring — root anywhere in the word
слово слово    phrase — consecutive words
# comment
```

Exact enumerations exist where a stem would collide with innocent words
(крест→крестьянин, культ→культура, *монстр*→демонстрация…). Never
auto-"optimize" or collapse entries. Some common-word collisions are
by design (обожаю, чудом, верю…). The editor runs tidy
(lowercase, ё→е, dedupe, sort) on every save.

## Milestones

1. ✅ Engine vendoring + refactor
2. ✅ Minimal GUI: local files, list selection, whisper run with progress
   (`python -m wordmute_app` from the repo root)
3. ✅ Queue + pass-plan builder + settings
4. ✅ yt-dlp URL flow (format picker → download → pipeline)
5. Review screen (cached transcript, snippet playback, un-mute, re-render)
6. GigaAM onboarding wizard (HF token) + GPU detection/warnings
7. Extras: word tester, transcript/SRT, beep mode, watch folder,
   model manager, history, RU/EN UI
8. Packaging (PyInstaller + Inno Setup) + licensing checklist
