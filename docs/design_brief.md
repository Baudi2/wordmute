# WordMute — UI/UX design brief

Package for a design session: attach this file **and the 9 screenshots
in `docs/design/`**. Everything the designer needs to know about the
product, the users, the current UI, and the hard constraints is below.

## Suggested prompt to start the design session

> Redesign the UI/UX of WordMute, a Windows desktop app (attached:
> design brief + screenshots of every current screen). Deliver: (1) a
> visual direction (colors, type, spacing, iconography, light + dark),
> (2) restructured layouts for the main window and each dialog, as
> mockups, (3) a Qt Style Sheet (QSS) theme implementing the direction,
> (4) empty-state and first-run designs. Respect every constraint in
> the brief — especially: Qt Widgets only (no web views, no QML), all
> current functionality stays, RU/EN localization, and the app's honest
> tone about imperfect speech recognition.

## 1. What the app is

WordMute takes a video/audio file (or a URL to download), transcribes
it locally with AI speech recognition, finds unwanted words/phrases
from a user-editable list, and mutes exactly those moments — video
untouched, only audio re-encoded. Runs fully offline after models are
downloaded. Nothing is uploaded anywhere.

Primary use: a user curates a personal word list (the shipped template
targets religious/mystical/occult vocabulary, ~4600 Russian + ~550
English entries) and runs their media library or freshly downloaded
videos through it, often unattended/overnight.

## 2. Users and tone

- Primary: Russian-speaking, **non-technical** Windows users. The
  original developer is the power user; the app is being polished for
  distribution to others.
- The interface exists in EN and RU (RU matters most).
- Tone: calm, honest, never magical. Speech recognition can miss
  mumbled/overlapping speech — the UI must never promise 100% catch
  rate. Multi-pass processing and the review screen exist precisely
  because of this; the design should present them as trust-building
  features, not fine print.

## 3. Hard constraints (violating these makes the design unusable)

1. **PySide6 / Qt Widgets.** Styling via QSS (Qt's CSS dialect),
   QPalette, and icons. No QML, no web views, no Electron-style
   rethinking. Custom-painted widgets are possible but each one costs
   maintenance — prefer QSS + layout changes.
2. **All current functionality stays.** Controls can move, merge, or
   collapse behind progressive disclosure, but nothing is removed.
3. **RU/EN strings** come from a simple dictionary (`ui/i18n.py`);
   Russian strings run ~30-40% longer — layouts must tolerate that.
4. Long-running work happens in the window: files process for minutes
   to hours. Progress, cancellation, and "what is it doing right now"
   are core UI, not chrome.
5. Windows 10/11 desktop, mouse-first, resizable window (min ~960px
   wide currently). Single main window + modal dialogs today; the
   designer may propose non-modal/docked alternatives within Qt's
   abilities.
6. File names are user content (long Russian titles) — truncation with
   tooltips, not overflow.

## 4. Current screens (screenshots in docs/design/)

The main window is a QTabWidget: Queue / Word Lists / Transcript /
Models / History. Flow steps (Settings, Add URL, per-file Review,
GigaAM setup) remain modal dialogs.

| # | File | Screen | Purpose |
|---|---|---|---|
| 1 | 01_queue_tab.png | Queue tab | Queue table (File/Duration/Status), add files/folder/URL, word-list checkboxes, pass-plan builder, Start/Cancel + overall progress, status line, scrolling log pane. Tools menu: watch folder toggle. |
| 2 | 02_wordlists_tab.png | Word Lists tab | In-app editor for both lists (combo to switch, live entry count, format hint line); Save auto-sorts/dedupes (lowercase, ё→е); Revert; plus the "why would this be muted?" tester with live results against the saved lists. |
| 3 | 03_transcript_tab.png | Transcript tab | Open a processed file → searchable transcript blocks from cache + SRT export; empty state when nothing opened. |
| 4 | 04_models_tab.png | Models tab | Whisper models: downloaded/size/download/delete; GigaAM cache size; GPU indicator. |
| 5 | 05_history_tab.png | History tab | Log of processed items (time, file, status, muted count, plan, output) + clear. |
| 6 | 06_settings.png | Settings dialog | Models (whisper + GigaAM), device, mute padding, whisper language, beep-instead-of-silence, VAD, downloads folder, cookies file (Netscape format, for logged-in sites like boosty.to), output location, interface language. |
| 7 | 07_add_url.png | Add URL dialog | Paste link → fetch format table (quality/ext/fps/type/size) or one-click "best quality". Uses the configured cookies file for gated sites. |
| 8 | 08_review.png | Review dialog | THE trust feature. Table of muted intervals (checkbox, times, pass, engine, words); clicking a row plays the original audio around it; uncheck false positives; "Re-render output" rebuilds in seconds. |
| 9 | 09_gigaam_wizard.png | GigaAM setup dialog | One-time onboarding for the optional, more-accurate Russian engine: 3 linked steps on Hugging Face, token paste + online validation, ffmpeg-shared check. |

## 5. Dynamic states the design must cover

Queue row Status cell (one line, changes live):
`queued` · `queued (720p mp4)` · `downloading 42% · 3.1 MB/s ·
~2 min 10 s left` · `processing…` · `pass 1/2 · transcribing 62% ·
~4 min 10 s left` · `pass 2/2 · matching…` · `muting… 64%` ·
`done → name.clean.mp4 — double-click to review` · `cancelled` ·
`error: <message>`.

Also: overall progress bar across files×passes; status line under it;
a yellow warning bar (GPU/VRAM/model-fit advice, GigaAM-setup-needed);
empty queue (no design at all today — first thing a new user sees);
log pane full of technical lines (currently the only place some
information lives).

Right-click on a finished row: Open output / Show output in folder /
Review.

## 6. Domain vocabulary (keep these concepts distinct)

- **Word list**: user-editable text file; entry types are meaningful
  notation shown as-is in the tester and review (`слово` exact,
  `корень*` stem, `*корень*` substring, `слово слово` phrase).
  Presented to new users as a *starting template*, not fixed policy.
- **Pass / pass plan**: ordered sequence of transcription passes;
  different engines catch different words. Whisper = zero-setup
  default, handles English/mixed; GigaAM = faster + more accurate for
  pure Russian, needs one-time setup.
- **Review / re-render**: post-run correction of false positives; fast
  because it reuses recorded data (never re-transcribes).
- **Output**: `<name>.clean.<ext>` next to the source (or a chosen
  folder).

## 7. Known UX debt (candid list — fix freely)

1. No first-run experience: empty window, zero guidance, template word
   lists never introduced.
2. Options row (word lists + plan builder) is dense and always fully
   visible even though most users set it once.
3. The log pane is developer-grade; useful facts (output location,
   intervals found) deserve first-class UI, not log lines.
4. Review — arguably the most important screen — is still a modal
   dialog (the tool screens are now tabs).
5. GigaAM wizard layout is broken-wide (see screenshot) and reads like
   documentation.
6. No dark mode; default Qt widget look throughout; no in-app
   iconography (text-only buttons); app icon exists
   (`packaging/wordmute.ico` — flat muted-speaker mark, recolorable).
7. Status cell packs pass/percent/ETA into one string — could be a
   per-row progress visual.
8. The word list editor is a bare QPlainTextEdit over a 4600-line
   file — usable, but scrolling/finding entries deserves design
   attention (search-in-list, grouping, virtualized list?).
9. No keyboard shortcuts, no drag-handle affordance for reordering
   passes (buttons only).
10. Warning bar is plain yellow text; easy to miss or to over-alarm.

## 8. What NOT to redesign

- Processing semantics, engine wording ("no engine guarantees 100%
  recall"), and the honest framing of trade-offs.
- The word-list entry notation (`*`-syntax) — it is user-facing data,
  not UI copy.
- File-naming scheme (`.clean` suffix) and sidecar files.

## 9. Where implementation hooks live (for the QSS deliverable)

- `wordmute_app/ui/` — one module per screen; widgets are named
  attributes (`self.start_button`, `self.warnings_label`, …) easy to
  target with QSS object names.
- App-wide stylesheet would be applied in `wordmute_app/main.py`
  (`app.setStyleSheet(...)`); none exists yet.
- Strings: `wordmute_app/ui/i18n.py` (EN keys → RU values).
- Icon source: `scripts/make_icon.py` (QPainter-drawn, easy to restyle).
