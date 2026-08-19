# WordMute — screen inventory (0.6.1 design round applied)

Every screen, tab, dialog, menu and notification the app can show.
Rendered by `scripts/render_screenshots.py` with staged demo data
(no real user data), 2× pixel density, **Russian UI** — Russian is the
primary audience and its strings run ~40 % longer than English, so
these are the worst case for layout.

Windows desktop app, PySide6 (Qt Widgets), "Nocturne" theme, dark by
default, light switchable at runtime. Sheets load in the order
`wordmute.qss` → `wordmute-setup.qss` → `wordmute-0.6.1.qss`.

| # | File | What it is |
|---|---|---|
| 00 | `00_queue_empty.png` | Queue, empty — now a real drop zone (1g) |
| 01 | `01_queue_empty_drag.png` | The same zone while three files hover over it |
| 02 | `02_queue_running.png` | Queue with 4 cards: done / transcribing / downloading / queued |
| 03 | `03_queue_log_open.png` | Same, with the «Подробности» log drawer expanded |
| 04 | `04_queue_setup_panel.png` | Same, with the «Изменить…» panel open (word lists + pass plan) |
| 05 | `05_queue_card_menu.png` | Per-card ⋯ menu, themed (1a); destructive rows carry a red trash icon |
| 06 | `06_queue_card_menu_language.png` | Its «Язык обработки» submenu with our check glyph |
| 07 | `07_tab_wordlists.png` | Word Lists after 1f: one toolbar row, one ribbon, editor ~90px taller, single-line tester |
| 08 | `08_tab_wordlists_syntax.png` | The syntax legend, now a popover behind «?» |
| 09 | `09_tab_transcript_empty.png` | Transcript empty state (same shell, `accepts="false"`) |
| 10 | `10_tab_transcript.png` | Transcript browser with a cached transcript |
| 11 | `11_tab_models.png` | Models: Whisper table, GigaAM cache, disk usage, update/repair |
| 12 | `12_tab_history.png` | History after 1d: locale dates, no ✓/✗ column, «ошибка» in Заглушено |
| 13 | `13_tab_settings.png` | Settings after 1e: «100 мс», «1000 Гц» |
| 14 | `14_dialog_add_url_single.png` | Add URL — one link, format table |
| 15 | `15_dialog_add_url_batch.png` | Add URL — batch after 1c: input sized to content, host chips, count on the button |
| 16 | `16_dialog_review.png` | Review dialog: intervals, waveform, re-render/SRT |
| 17 | `17_dialog_delete_files.png` | Delete confirmation — our own `QDialog#wm_confirm`, not QMessageBox |
| 18–25 | `18_wizard_0_intro` … `25_wizard_7_install` | Setup wizard, 8 steps; the install page after 1b (docked log, 30px rows) |
| 26 | `26_toast_finished.png` | In-app toast |
| 27–29 | `27_light_queue`, `28_light_settings`, `29_light_history` | Light theme, main screens |
| 30 | `30_light_wizard_whisper.png` | Light theme, wizard |

## The seven weak points — what was done

1. **Menus and confirmations (1a)** — `themed_menu()` makes every menu
   frameless + translucent so the platform rim and native shadow stop
   leaking around our corners; the sheet owns `::indicator` (check.svg)
   and `::right-arrow` (chevron-right.svg). Every `QMessageBox` is
   replaced by `QDialog#wm_confirm`, whose primary button names the
   action («В Корзину», «Удалить модель», «Прервать»); `qtbase_ru.qm`
   ships with the app for the native file dialogs.
   *Deviation:* red TEXT on destructive menu items is impossible in Qt
   — QSS sub-control selectors read the menu widget's properties, not
   the QAction's. They carry a red trash icon instead.
2. **Install page (1b)** — the page left the shared scroll area: head
   and progress fixed, only the rows scroll, log docked at the bottom
   (24px disclosure + 118px pane, with Копировать / Открыть файл). Rows
   are 30px, the percent moved into the row and the moving detail
   («Сейчас: Whisper · 992 МБ из 1,5 ГБ · 8,2 МБ/с») into the subtitle.
   With the log closed all six rows fit; open, four of six stay visible
   (the mock predicted five — our head block is one line taller).
   The log state is remembered in settings.json, and a failure turns
   «Прервать» into «Повторить».
3. **Batch Add-URL (1c)** — the input is sized to its content (3–8
   lines, then it scrolls) instead of eating the dialog; one chip per
   host plus a warn chip counting lines that are not links; summary on
   the left of the footer and the count on the button.
4. **History dates (1d)** — QLocale, with today/yesterday branches, the
   full stamp in the tooltip and the ISO string in `Qt.UserRole`.
5. **Unit suffixes (1e)** — set in `retranslate_ui()` with NBSP and no
   group separator; sizes and rates go through one locale-aware helper.
6. **Word Lists (1f)** — three explanatory rows became one toolbar; the
   legend is a Popup `QFrame` with a two-column grid; the ribbon is one
   32px line dismissed per list; the tester is one row with the first
   hit inline and the breakdown in its tooltip.
7. **Empty states (1g)** — `QFrame#drop_zone` fills the queue page, and
   a hovering drag repaints it with the accepted-file count; the
   transcript tab reuses the shell with `accepts="false"`. The muting
   explanation moved to the Start button's tooltip.

## Second live round (real-app feedback)

Fixes after the user ran the branch: host chips are true pills with the
mock's 5px dot (Qt silently draws SQUARE corners when border-radius
exceeds half the widget height — the chips needed a fixed 28px height);
a wrapping FlowLayout keeps many chips from clipping the warning; the
warning and the footer count use real Russian plurals («1 строка не
похожа…» / «5 строк не похожи…») via the new `tr_plural()`; Enter adds
a line in batch mode and pastes land on their own line, so hand-typing
a link into a list works; the batch input opens at its full 10-line
height; the footer is [summary] … [Отмена] [Добавить N в очередь]; the
single-link window implements mock 2b (darker list tail, fading
end-of-list line, «Это все форматы…», pinned «Выбрано: …» row); the «?»
popover closes on the second click; the queue and transcript empty
states use the mock's SVG icons; the tester input carries the mock's
magnifier and placeholder.

## Deliberate deviations from the handoff

- State lives in the app's `settings.json` (`%APPDATA%\WordMute`), not
  in `QSettings` — the wizard, the log dock and the per-list ribbon
  dismissal all use the existing store.
- i18n uses the app's own `tr()` dictionary rather than Qt `.qm`
  catalogs; `qtbase_ru.qm` is loaded only for Qt's own dialogs.
- Counts now resolve real Russian plural forms through `tr_plural()`
  (one/few/many); the earlier plural-dodging phrasing is gone.
