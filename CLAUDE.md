# WordMute — context for Claude sessions

Windows desktop app (PySide6) that mutes unwanted words in video/audio:
local ASR (faster-whisper / GigaAM) → match against user word lists →
ffmpeg mutes intervals, video copied untouched. Fully offline. The user
(badic) is Russian-speaking; the app ships EN/RU and RU matters most.

## Read first
- README.md is the PUBLIC repo front page (RU-first) — keep it
  user-facing; docs/DEVELOPMENT.md holds engine rules, layout,
  milestone history (all 8 done)
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
  hf_setup, history, models, transcript, probe, jobs, updates (PyPI/HF
  version checks), runtime_env (slim-installer managed runtime, see
  below).
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
- INVIOLABLE thread rule: every QThread worker starts via
  ui/threads.start_thread(owner, thread) and close-time waits go
  through wait_thread(). A parentless QThread whose last Python ref is
  dropped in its result slot (`self._worker = None`) is deleted while
  Qt still counts it running → qFatal "QThread: Destroyed while thread
  is still running" → the app vanishes with exit 0xC0000409, no
  traceback. Reproduced on «Проверить обновления»; tests/test_threads.py
  guards it.

## Commands
- Tests: `python -m pytest tests` (150+, all offscreen/stubbed, no
  network; run from repo root)
- Run app: desktop shortcut (pythonw, dev mode, GigaAM works) or
  `python -m wordmute_app`
- Screenshots for design round-trips: `python scripts/render_screenshots.py`
  (writes docs/design/*.png with staged fake data)
- Package: `powershell -File packaging\build.ps1` → dist\WordMute
  (~450 MB) + Inno installer (~160 MB, packaging\Output). SLIM build:
  engine packages (whisper stack, yt-dlp, GigaAM) and ffmpeg are NOT
  frozen — first run shows SetupDialog which downloads them into
  %LOCALAPPDATA%\WordMute\runtime (core/runtime_env.py). The spec
  bundles the COMPLETE stdlib (a partially bundled stdlib package
  shadows the runtime fallback — yt-dlp broke on html.parser without
  this) and excludes all engine packages. Frozen diagnostics:
  `$env:WORDMUTE_RUNTIME_REPORT="r.json"; WordMute.exe` writes status
  + import probes; `WORDMUTE_SMOKE=1` = start-and-exit smoke test.
  docs/INSTALL_GUIDE.md ships in the installer — bilingual: RU user
  steps + EN "For the AI assistant" support brief (hosts, pitfalls,
  clean-retry = delete runtime dir). Keep it in sync with
  runtime_env.py changes.

## State / open items
- v0.3.0 SLIM installer built and machine-verified: real bootstrap of
  the managed runtime succeeded and the frozen exe imports
  faster_whisper + yt_dlp from it (report mode) and passes the smoke
  test. Still untested by a real user: full transcription run from the
  frozen build, and the first-run SetupDialog flow on a clean PC.
- SHIPPED 2026-08-09: public repo github.com/Baudi2/wordmute (branch
  master), release v0.3.0 with the installer asset, landing page live
  at https://baudi2.github.io/wordmute/ (Pages from master:/docs).
  docs/index.html embeds INSTALL_GUIDE (copy-for-AI button) — keep
  both in sync; the download button auto-resolves the latest
  release's .exe via the GitHub API, so new releases need no site
  edits, just tag + upload.
- Fat 0.2.0 installer still in packaging\Output as fallback.
- v0.4.0 roadmap COMPLETE (all 10 items): keep-awake, finish
  notification, window clamp, repair-components button, disk-usage
  line in Models, traffic stat in History («скачано за месяц»), app
  self-update check (wordmute_app.__version__ = single version
  source, build.ps1 injects it into Inno; quiet startup check +
  Models-tab line; WORDMUTE_NO_UPDATE_CHECK disables), model-size
  choice in SetupDialog, background thumbnailing for bulk adds
  (WORDMUTE_SYNC_PROBE forces sync in tests), multi-URL paste in Add
  URL (batch mode = best quality each; playlists still rejected).
  SHIPPED 2026-08-11: release v0.4.0 published with the installer
  asset (157.7 MB), machine-verified (frozen runtime imports + smoke
  + live download link); site/README/INSTALL_GUIDE refreshed for
  0.4.0 incl. the page-embedded guide copy. Caveat learned: anonymous
  GitHub API = 60 req/h per IP — never poll it in tight loops from
  the dev machine; the app's check_app_update degrades silently by
  design when rate-limited.
- Research plan 2026-08 (full report: .claude/research-2026-08.md,
  gitignored; user approved doing ALL of it). DONE: bug fixes
  (GigaAM install channel PyPI→pinned GitHub archive — PyPI 0.1.0
  was broken for users; default gigaam_model v3_e2e_rnnt→v3_rnnt),
  Package А (large-v3-turbo model option, int8_float16 on GPU,
  concurrent_fragment_downloads=4, stage-timing report in History
  tooltips), Package Б (opt-in batched «быстрый режим» — needs an
  A/B on a real RU video with the user before recommending).
  Package В DONE: GigaAM now runs via onnx-asr (engine backend
  selector, CLI default torch / app auto-prefers onnx; component =
  onnx-asr[cpu,hub] ~60 МБ + ~850 МБ model on first use; no HF
  token — wizard gates only the legacy torch path; verified with
  real inference end-to-end incl. matching). Package Г DONE:
  pyqttoast toasts (Nocturne-styled, ui/toasts.py; new frozen deps
  pyqt-toast-notification + QtPy, both MIT), review waveform strip
  (ui/waveform.py — ffmpeg peaks, no numpy), skeleton shimmer on
  bulk-add cards; QtAwesome deliberately skipped (icon consistency).
  Package Д code items DONE: fade-edged mutes (40 ms ramps, CLI
  first + vendored; asetnsamples=256 because volume exprs eval
  per-FRAME — verified acoustically on decoded PCM) and «Сохранить
  SRT» in the review dialog. Д3 strictness presets and Д4 subtitle
  import are DELIBERATELY parked pending user decisions (presets
  need the user to curate severity categories in THEIR lists;
  subtitle import conflicts with word-precision muting — phrase-
  level cues would mute whole sentences). SHIPPED 2026-08-12:
  release v0.5.0 published (installer 160 MB; frozen report probes
  all green incl. onnx_asr; smoke ok; site refreshed; download link
  verified). The in-app update check was confirmed LIVE: a simulated
  0.4.0 detects 0.5.0 with the correct release URL. Still pending:
  A/B of «быстрый режим» on a real RU video (user).
- v0.6.0 SHIPPED 2026-08-18 (19 commits since 0.5.0). Night-batch
  fixes: continuous download pump (was one-ahead), per-item language
  profiles «Язык обработки» in the card ⋯ menu (mixed RU/EN queues;
  auto detection deliberately rejected — mixed-speech videos),
  delete-source protected when no .clean copy exists, batch links get
  real video names. Tester round: first run follows the OS language,
  batch adds take a quality cap instead of forced best, multi-URL
  input is one link per line, ffmpeg download retries + GitHub
  mirror, GigaAM back on the GPU when torch+CUDA are there, GigaAM
  onnx sentence-splitting fixed (SentencePiece «▁» token shape).
  Setup became the 8-step wizard (everything downloads during setup,
  ffmpeg has no checkbox, GigaAM pre-checked and no longer labelled
  experimental, HF-token wizard deleted). Plus the full screenshot
  set (docs/design + SCREENS.md) and the leftover-JSON fix
  (drop_output_caches). Installer 160 MB, frozen report all green,
  smoke ok.
- Weak points queued for the design round (docs/design/SCREENS.md):
  unthemed QMenu/QMessageBox with English Yes/No in a RU UI (needs
  qtbase_ru bundled), install page overflows with the log open,
  batch Add-URL is mostly empty space, History dates use the C
  locale, «100 ms»/«1000 Hz» suffixes untranslated, Word Lists tab
  dense, empty states have no anchor.
- Other open items: LICENSE file decision (repo is public with no
  license = all-rights-reserved; user undecided), GigaAM frozen-build
  end-to-end still untested (install channel now fixed; torch is
  CPU-only from pip — solved properly by Package В), Inter fonts only
  partially referenced by QSS weights.
