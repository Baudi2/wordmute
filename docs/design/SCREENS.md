# WordMute — screen inventory (v0.5.1, pre-release)

Every screen, tab, dialog, menu and notification the app can show.
Rendered by `scripts/render_screenshots.py` with staged demo data
(no real user data), 2× pixel density, **Russian UI** — Russian is the
primary audience and its strings run ~40 % longer than English, so
these are the worst case for layout.

Windows desktop app, PySide6 (Qt Widgets), "Nocturne" theme, dark by
default, light switchable at runtime. Fixed values in the QSS are
logical px (DPI-safe).

| # | File | What it is |
|---|---|---|
| 00 | `00_queue_empty.png` | Queue tab, empty state — the app's first screen |
| 01 | `01_queue_running.png` | Queue with 4 cards: done / transcribing / downloading / queued, run bar at the bottom |
| 02 | `02_queue_log_open.png` | Same, with the «Подробности» log drawer expanded |
| 03 | `03_queue_setup_panel.png` | Same, with the «Изменить…» panel open (word lists + pass plan chips) |
| 04 | `04_queue_card_menu.png` | Per-card ⋯ context menu (all items force-enabled for the shot) |
| 05 | `05_queue_card_menu_language.png` | Its «Язык обработки» submenu (per-video RU/EN profile) |
| 06 | `06_tab_wordlists.png` | Word Lists tab: list picker, syntax hint, dismissible template note, editor, match tester |
| 07 | `07_tab_transcript.png` | Transcript tab: cached transcript browser + SRT export |
| 08 | `08_tab_models.png` | Models tab: Whisper model table, GigaAM cache, disk usage, update/repair buttons |
| 09 | `09_tab_history.png` | History tab: processed items, ✓/✗ status glyph, files-on-disk glyph (●/◐/○), monthly traffic |
| 10 | `10_tab_settings.png` | Settings tab: recognition, muting, files/downloads, theme, UI language |
| 11 | `11_dialog_add_url_single.png` | Add URL — one link, format table fetched by yt-dlp |
| 12 | `12_dialog_add_url_batch.png` | Add URL — batch mode (one link per line, one quality for all) |
| 13 | `13_dialog_review.png` | Review dialog (non-modal): interval table, waveform strip, re-render/SRT actions |
| 14 | `14_dialog_delete_files.png` | Delete-files confirmation (QMessageBox) |
| 15–22 | `15_wizard_0_intro` … `22_wizard_7_install` | First-run component wizard, all 8 steps: intro → Python → Whisper → yt-dlp → ffmpeg → GigaAM → review → installing |
| 23 | `23_toast_finished.png` | In-app toast (pyqttoast, Nocturne-styled) |
| 24–26 | `24_light_queue`, `25_light_settings`, `26_light_history` | Light theme, main screens |
| 27 | `27_light_wizard_whisper.png` | Light theme, wizard (Whisper step) |

## Known weak points (candidates for the rework)

Found while producing this set; none of them are staging artifacts.

1. **QMenu and QMessageBox are unthemed** (`04`, `05`, `14`) — the card
   menu and the delete confirmation still use the platform look:
   flat grey menu, blue system "?" icon, and Qt's standard buttons
   render as English **Yes/No** in a Russian UI (Qt's own `qtbase_ru`
   translation is not installed; it also has to be bundled into the
   frozen build).
2. **Install page overflows** (`22`) — with the log expanded the page
   scrolls at the default 920×620 wizard size; the log ends up below
   the fold exactly when the user wants it.
3. **Batch Add-URL is mostly empty space** (`12`) — the growing input
   takes the whole dialog even for four links; the quality row and
   cookies hint sit far from the eye.
4. **History dates are English** (`09`) — `16 Aug 22:35` comes from
   `strftime("%d %b")`, i.e. the C locale, in an otherwise Russian UI.
5. **Unit suffixes stay English** (`10`) — «100 ms», «1000 Hz» instead
   of мс / Гц.
6. **Word Lists tab is dense** (`06`) — three stacked explanatory rows
   (syntax legend, template note, tester hint) before the editor.
7. **Empty queue and empty transcript have no visual anchor** (`00`,
   `07`) — large blank areas, drop target not obvious.
