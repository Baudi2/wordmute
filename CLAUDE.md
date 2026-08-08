# WordMute — context for Claude sessions

Windows desktop app (PySide6) that mutes unwanted words in video/audio:
local ASR (faster-whisper / GigaAM) → match against user word lists →
ffmpeg mutes intervals, video copied untouched. Fully offline. The user
(badic) is Russian-speaking; the app ships EN/RU and RU matters most.

## Read first
- README.md — milestones (all 8 done), engine rules, layout
- docs/design_brief.md — screens, states, constraints
- docs/LICENSING.md — pre-release redistribution checklist
- git log — every step has a detailed commit message

## Inviolable rules
- `wordmute_app/engine/wordmute.py` is vendored from the user's daily
  CLI (`C:\wordmute\wordmute.py`). Matching logic (norm / load_wordlist
  / parse_wordlist_lines / find_hits) must NEVER diverge — parity tests
  in tests/test_parity_with_cli.py compare against the original.
- Word lists: entry types (`слово`, `корень*`, `*корень*`, phrases) are
  deliberate; never auto-"optimize". Known collisions (обожаю, чудом,
  верю…) are BY DESIGN. Lists are user-editable templates.
- ё→е normalization everywhere text is compared.
- Review re-renders mute the ORIGINAL source (muting never shifts the
  timeline); never re-transcribe for an un-mute edit.
- Audio codec must follow the output container (webm→opus etc.,
  `_AUDIO_CODEC_FOR` in the engine) — AAC into webm fails.

## Working agreements (from the user)
- Work milestone-by-milestone; commit each step with a real message
  (commit via `git commit -F <file>` — inline here-strings with quotes
  get mangled by the shell wrapper).
- UI texts must be translated (ui/i18n.py `tr()` dict, EN keys → RU);
  RU runs ~40% longer — layouts must tolerate it. Statuses/log lines
  use humanized times ("1 min 29 s" / "1 ч 5 мин").
- Design iterations come as zips from an external design session
  ("Nocturne" theme). IMPORTANT: new QSS drops silently revert our
  local merges — reapply: (1) NO per-cell item:hover (row hover is done
  in code via ui/hover_table.py), (2) thin column separators
  (border-right on table items), (3) transparent #pass_chips chrome.
  Local merges are marked with "local merge:" comments in the QSS.
- Fixed pixel values are logical px (DPI-safe); the real hazards are
  Windows text-only scaling and small screens (initial-size clamp is a
  known TODO).

## Architecture map
- engine/ — vendored CLI + wordlist_tidy; reporter events via
  set_reporter (GUI subscribes); global no-console-window patching in
  core/proc.py (GigaAM/pyannote spawn their own ffmpeg).
- core/ — Qt-free: config (settings.json in %APPDATA%\WordMute,
  hf_token.txt separate), downloader (yt-dlp API + cookies_file for
  Boosty etc.), review sidecars (<out>.wordmute.json), thumbs, gpu,
  hf_setup, history, models, transcript, probe, jobs.
- ui/ — sidebar nav (SidebarNav mimics QTabWidget API; pages: Queue /
  Word Lists / Transcript / Models / History / Settings), queue = card
  list (QueueCard/QueueList), plan = vertical chip column, theme.py
  loads resources/theme/*.qss (dark default, light switchable live,
  Inter fonts bundled), review dialog is non-modal.
- Qt gotchas already hit: clicked(bool) leaking into optional params
  (connect via lambda), row sizing ignores cell widgets (size rows to
  button height), item widgets follow item sizeHint (QueueList syncs to
  viewport width), setItemWidget widgets die on drag-move (rebuild on
  rowsMoved), screenshots need show()+processEvents before grab.

## Commands
- Tests: `python -m pytest tests` (150+, all offscreen/stubbed, no
  network; run from repo root)
- Run app: desktop shortcut (pythonw, dev mode, GigaAM works) or
  `python -m wordmute_app`
- Screenshots for design round-trips: `python scripts/render_screenshots.py`
  (writes docs/design/*.png with staged fake data)
- Package: `powershell -File packaging\build.ps1` → dist\WordMute
  (whisper-only, ~3 GB) + Inno installer. GigaAM is NOT in the frozen
  build (v2 plan in docs/LICENSING.md); dev shortcut has it.

## State / open items
- v1 installer built & verified to launch; a real frozen transcription
  run is still untested by the user.
- Open TODOs: clamp initial window size to screen, background
  thumbnailing for bulk folder adds, playlist support in Add URL,
  Inter fonts only partially referenced by QSS weights.
