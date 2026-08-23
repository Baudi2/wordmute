"""Minimal interface localization (English / Russian).

tr() maps English source strings to Russian when the language setting
is 'ru'. First pass covers the window/dialog chrome and common
statuses; log lines stay English. Untranslated strings fall through
unchanged, so adding keys is always safe."""

_LANG = "en"


def set_language(lang: str) -> None:
    global _LANG
    _LANG = lang if lang in ("en", "ru") else "en"


def current_language() -> str:
    return _LANG


def tr(text: str) -> str:
    if _LANG == "ru":
        return RU.get(text, text)
    return text


def tr_plural(key: str, n: int) -> str:
    """Count-aware translation: Russian needs three forms («1 строка» /
    «2 строки» / «5 строк»), which a plain key dict cannot express —
    «строк не похожи на ссылки: 1» read as broken Russian. English uses
    the first form for 1, the last for everything else."""
    forms = PLURALS.get(key, {}).get(_LANG)
    if not forms:
        return key.format(n)
    if _LANG == "ru":
        if n % 10 == 1 and n % 100 != 11:
            form = forms[0]
        elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            form = forms[1]
        else:
            form = forms[2]
    else:
        form = forms[0] if n == 1 else forms[-1]
    return form.format(n)


PLURALS = {
    "{} links": {
        "en": ("{} link", "{} links"),
        "ru": ("{} ссылка", "{} ссылки", "{} ссылок"),
    },
    "{} lines are not links": {
        "en": ("{} line is not a link — it will be skipped",
               "{} lines are not links — they will be skipped"),
        "ru": ("{} строка не похожа на ссылку — будет пропущена",
               "{} строки не похожи на ссылки — будут пропущены",
               "{} строк не похожи на ссылки — будут пропущены"),
    },
    "{} files join the queue": {
        "en": ("Release — {} file joins the queue",
               "Release — {} files join the queue"),
        "ru": ("Отпустите — {} файл попадёт в очередь",
               "Отпустите — {} файла попадут в очередь",
               "Отпустите — {} файлов попадут в очередь"),
    },
    # word lists: the find bar's filter count and the tester's
    # «also in N lists» (design round 4)
    "{} lines": {
        "en": ("{} line", "{} lines"),
        "ru": ("{} строка", "{} строки", "{} строк"),
    },
    "· also in {} lists": {
        "en": ("· also in {} list", "· also in {} lists"),
        "ru": ("· ещё в {} списке", "· ещё в {} списках",
               "· ещё в {} списках"),
    },
    # queue: what a drop / file dialog left out
    "{} already-processed files (.clean) skipped": {
        "en": ("{} already-processed file (.clean) skipped — add the "
               "original video instead",
               "{} already-processed files (.clean) skipped — add the "
               "original videos instead"),
        "ru": ("{} уже обработанный файл (.clean) пропущен — добавьте "
               "исходное видео",
               "{} уже обработанных файла (.clean) пропущены — добавьте "
               "исходные видео",
               "{} уже обработанных файлов (.clean) пропущены — добавьте "
               "исходные видео"),
    },
    "{} files are not media": {
        "en": ("{} file is not a media file — skipped",
               "{} files are not media files — skipped"),
        "ru": ("{} файл — не медиафайл, пропущен",
               "{} файла — не медиафайлы, пропущены",
               "{} файлов — не медиафайлы, пропущены"),
    },
    "{} files already in the queue": {
        "en": ("{} file is already in the queue",
               "{} files are already in the queue"),
        "ru": ("{} файл уже в очереди", "{} файла уже в очереди",
               "{} файлов уже в очереди"),
    },
}


RU = {
    # main window
    "Add Files": "Добавить файлы",
    "Add Folder": "Добавить папку",
    "Remove Selected": "Убрать выбранное",
    "GigaAM Setup": "Настройка GigaAM",
    "Watch Folder": "Следить за папкой",
    "File": "Файл",
    "Duration": "Длительность",
    "Status": "Статус",
    "Word lists": "Списки слов",
    "Russian list": "Русский список",
    "English list": "Английский список",
    "Force all passes": "Все проходы принудительно",
    "Ignore cached transcripts": "Игнорировать кэш транскриптов",
    "Pass plan": "План проходов",
    "Add Whisper pass": "Добавить проход Whisper",
    "Add GigaAM pass": "Добавить проход GigaAM",
    "Remove": "Убрать",
    "Move Up": "Вверх",
    "Move Down": "Вниз",
    "Start": "Старт",
    "Cancel": "Отмена",
    "Ready.": "Готово к работе.",
    "queued": "в очереди",
    "processing…": "обработка…",
    "done": "готово",
    "done — double-click to review": "готово — двойной клик для проверки",
    "double-click to review": "двойной клик для проверки",
    "Open output": "Открыть результат",
    "Show output in folder": "Показать результат в папке",
    "muting…": "заглушение…",
    "cancelled": "отменено",
    "Cancelling…": "Отмена…",
    "Tools": "Инструменты",
    "Stop Watching": "Перестать следить",
    "More": "Ещё",
    "Open": "Открыть",
    "Retry": "Повторить",
    "Open review file…": "Открыть файл проверки…",
    "Frequency:": "Частота:",
    "GigaAM passes need a one-time Hugging Face setup — "
    "click 'GigaAM Setup'.":
        "Проходам GigaAM нужна разовая настройка Hugging Face — "
        "нажмите «Настройка GigaAM».",
    "GigaAM support is not installed in this build — GigaAM "
    "passes will fail. Use Whisper passes instead.":
        "Поддержка GigaAM не установлена в этой сборке — проходы "
        "GigaAM не сработают. Используйте проходы Whisper.",
    # tabs
    "Queue": "Очередь",
    "Word Lists": "Списки слов",
    "Transcript": "Транскрипт",
    "Models": "Модели",
    "History": "История",
    # word list editor
    "Save (auto-sort)": "Сохранить (с сортировкой)",
    "Revert": "Отменить правки",
    "Why would this be muted?": "Почему это заглушится?",
    "checks the saved lists — save your edits first":
        "проверка по сохраненным спискам — сначала сохраните правки",
    "The word list has unsaved changes. Save them?":
        "В списке слов есть несохраненные изменения. Сохранить?",
    # transcript tab
    "Open Media…": "Открыть файл…",
    "No file opened.": "Файл не открыт.",
    "Open a processed media file to view its transcript "
    "(the cache appears after transcription).":
        "Откройте обработанный файл, чтобы посмотреть его транскрипт "
        "(кэш появляется после транскрибации).",
    # settings
    "Cookies file:": "Файл cookies:",
    "(optional)": "(необязательно)",
    "Recognition": "Распознавание",
    "Muting": "Заглушение",
    "Files && downloads": "Файлы и загрузки",
    "Theme:": "Тема:",
    "Dark": "Темная",
    "Light": "Светлая",
    "Saved": "Сохранено",
    "Used for members-only downloads (e.g. Boosty) — exported "
    "from your browser.":
        "Нужен для загрузок по подписке (например, Boosty) — "
        "экспортируется из браузера.",
    # queue chrome
    "Change…": "Изменить…",
    "Hide": "Скрыть",
    "Details": "Подробности",
    "Russian": "Русский",
    "English": "Английский",
    "none": "нет",
    "empty": "пусто",
    "Drop video or audio files here":
        "Перетащите сюда видео или аудио",
    "…or paste a link with Add URL. Matched words from your word "
    "lists are muted; the video stays untouched.\n"
    "Everything runs on this computer — nothing is uploaded.":
        "…или вставьте ссылку через «Добавить ссылку». Совпавшие слова "
        "из ваших списков заглушаются; видео не изменяется.\n"
        "Все происходит на этом компьютере — ничего не загружается в сеть.",
    "View word lists": "Открыть списки слов",
    # word lists tab
    "Find in list… (Enter = next)": "Поиск по списку… (Enter = дальше)",
    "This is the shipped template — one person's curated "
    "starting point. Edit freely; it's your list.":
        "Это стартовый шаблон — чьи-то личные настройки. Смело "
        "редактируйте; это ваш список.",
    "Testing your current edits (saved or not) "
    "plus the other saved list.":
        "Проверка по текущим правкам (даже несохраненным) "
        "плюс другой сохраненный список.",
    "Hide this note": "Скрыть эту подсказку",
    # add URL: batch mode + the 2b single-link tail
    "Add {} to the queue": "Добавить {} в очередь",
    "That's every format this site offered — {}":
        "Это все форматы, которые отдал этот сайт — {}",
    "Need another option? A cookies file sometimes helps":
        "Нужен другой вариант? Иногда помогает файл cookies",
    "Selected:": "Выбрано:",
    "recommended": "рекомендуется",
    # updates: live progress + the 403 hint
    "Updating {}…": "Обновление {}…",
    "Updating the {} model…": "Обновление модели {}…",
    "this usually means yt-dlp needs updating: Models tab → Check for "
    "updates → Update all, then restart the app. Retrying once also "
    "sometimes helps.":
        "обычно это значит, что yt-dlp пора обновить: вкладка «Модели» "
        "→ «Проверить обновления» → «Обновить все», затем перезапустите "
        "приложение. Иногда помогает и простой повтор.",
    # models tab regroup (design models-tab-handoff.md)
    "recognition runs on the graphics card": "распознавание идёт на видеокарте",
    "No NVIDIA GPU found — recognition runs on the processor, 2–4× "
    "slower":
        "NVIDIA GPU не найден — распознавание на процессоре, в 2–4 раза "
    "медленнее",
    "Open settings →": "Открыть настройки →",
    "Recognition models": "Модели распознавания",
    "what is downloaded and how much disk it takes": "что скачано и сколько занимает на диске",
    "State": "Состояние",
    "GIGAAM · RUSSIAN ENGINE": "GIGAAM · РУССКИЙ ДВИЖОК",
    "failed — {}": "не удалось — {}",
    "Model downloaded": "Модель скачана",
    "Delete…": "Удалить…",
    "Delete the GigaAM model caches?": "Удалить кэши моделей GigaAM?",
    "Disk usage · {}": "Занято на диске · {}",
    "components": "компоненты",
    "Maintenance": "Обслуживание",
    "updates and repair of the install": "обновления и ремонт установки",
    "checked {}": "проверено {}",
    "checking for updates…": "проверка обновлений…",
    "Update all ({})": "Обновить все ({})",
    "Press «Check for updates» to see whether newer versions of the "
    "engines and models exist.":
        "Нажмите «Проверить обновления», чтобы узнать, есть ли новые версии "
    "движков и моделей.",
    "GigaAM weights update together with the onnx-asr package.": "Веса GigaAM обновляются вместе с пакетом onnx-asr.",
    "Add components…": "Доустановить компоненты…",
    "the wizard adds what is missing and leaves the rest alone": "мастер доставит пропущенное, установленное не тронет",
    "Repair components…": "Починить компоненты…",
    "clean start of the runtime": "чистый старт среды",
    "What's new": "Что нового",
    "up to date": "актуально",
    "Update": "Обновить",
    "{} model": "модель {}",
    "current revision": "текущая ревизия",
    "new revision": "новая ревизия",
    "updating {} of {}": "обновление {} из {}",
    "Updates installed": "Обновления установлены",
    "Update failed": "Не удалось обновить",
    "Delete the runtime and set it up again?": "Удалить среду выполнения и настроить заново?",
    "Word lists, settings, history and the downloaded models are kept. "
    "Best done right after starting the app, before any processing.":
        "Словари, настройки, история и скачанные модели сохранятся. Лучше "
    "делать сразу после запуска, до обработки.",
    "Delete and set up": "Удалить и настроить",
    # setup: the install page's moving detail line and log dock
    "Now: {}": "Сейчас: {}",
    "{} of {}": "{} из {}",
    "Copy": "Копировать",
    "Copied": "Скопировано",
    "Open file": "Открыть файл",
    "Setup stopped — see the log.":
        "Установка остановлена — подробности в журнале.",
    # empty states as drop targets (design 1g)
    "Drop video or audio here": "Перетащите сюда видео или аудио",
    "Or paste a link. Everything runs on this computer.":
        "Или вставьте ссылку. Всё считается на этом компьютере.",
    "Release — {} file(s) join the queue":
        "Отпустите — в очередь попадёт файлов: {}",
    "mp4 · mkv · mp3 — anything else is skipped":
        "mp4 · mkv · mp3 — остальное будет пропущено",
    "The transcript will appear here": "Здесь появится расшифровка",
    "Processed files open from here — or from History with a double "
    "click.":
        "Обработанные файлы открываются отсюда — или из истории "
        "двойным щелчком.",
    "Open History": "Открыть историю",
    "Words from your lists are muted in the audio; the video itself is "
    "copied untouched.":
        "Слова из ваших списков заглушаются в звуке; сам видеоряд "
        "копируется без изменений.",
    # word lists: one toolbar row + the syntax popover (design 1f)
    "Entry syntax": "Синтаксис записей",
    "ENTRY SYNTAX": "СИНТАКСИС ЗАПИСЕЙ",
    "exact word": "точное слово",
    "word starts with": "слово начинается с",
    "anywhere in the word": "в любом месте слова",
    "phrase": "фраза",
    "comment": "комментарий",
    "Saving sorts the list, lowercases it and removes duplicates.":
        "При сохранении список сортируется, приводится к нижнему "
        "регистру, дубликаты убираются.",
    "This is the shipped template — edit it freely, it's your list.":
        "Это стартовый шаблон — правьте свободно, это ваш список.",
    "Check a word or phrase against this list and the other saved "
    "one…":
        "Проверить слово или фразу по этому списку и другим "
        "сохранённым…",
    "(no match)": "(нет совпадений)",
    'phrase "{}"  ←  matched': 'фраза «{}»  ←  совпала',
    # word lists: find bar (design round 4, 1a + 1b) and the tester row
    "Find in list (Ctrl+F)": "Поиск по списку (Ctrl+F)",
    "Find…": "Найти…",
    "{} of {}": "{} из {}",
    "no matches": "нет совпадений",
    "Search finds list entries. To check whether a word gets muted, use "
    "the tester below.":
        "Поиск ищет записи списка. Проверить, заглушится ли слово, — "
        "в тестере внизу.",
    "Matches": "Совпадения",
    "Show only the matching lines": "Показать только строки с совпадениями",
    "Previous match (Shift+F3)": "Предыдущее совпадение (Shift+F3)",
    "Next match (F3)": "Следующее совпадение (F3)",
    "Close (Esc)": "Закрыть (Esc)",
    "showing {} of {} — filter by «{}» · editing off":
        "показаны {} из {} — фильтр по «{}» · редактирование выключено",
    "Show all": "Показать все",
    "will be muted": "заглушится",
    "will not be muted — no matches": "не заглушится — совпадений нет",
    # pre-0.7.0 audit fixes
    "Re-render in progress — wait for it to finish.":
        "Идёт пересборка — дождитесь её окончания.",
    "Output folder is not available: {}": "Папка результата недоступна: {}",
    "Restart WordMute first": "Сначала перезапустите WordMute",
    "The components are in use by this session. Restart the app and run "
    "the repair before processing anything.":
        "Компоненты заняты этим сеансом. Перезапустите приложение и "
        "запустите починку до любой обработки.",
    "Could not remove the runtime": "Не удалось удалить компоненты",
    "Something in it is still in use: {}\nRestart the app and try again.":
        "Что-то из них ещё используется: {}\nПерезапустите приложение и "
        "попробуйте снова.",
    "An update is installing.": "Устанавливается обновление.",
    "A model is downloading.": "Скачивается модель.",
    "Quitting interrupts it; you can run it again later.":
        "Выход прервёт это; можно будет запустить снова позже.",
    "Quit anyway": "Всё равно выйти",
    "Already in the queue: {}": "Уже в очереди: {}",
    "Nothing added": "Ничего не добавлено",
    "Some files were skipped": "Часть файлов пропущена",
    "next to the source": "рядом с исходником",
    # tier 3: captions and statuses that bypassed tr()
    "Watch folder": "Папка для отслеживания",
    "Add media files": "Добавить медиафайлы",
    "Add folder": "Добавить папку",
    "Open review file": "Открыть файл проверки",
    "Open media file": "Открыть медиафайл",
    "Media files ({})": "Медиафайлы ({})",
    "All files (*)": "Все файлы (*)",
    "WordMute review (*.wordmute.json)": "Файл проверки WordMute (*.wordmute.json)",
    "Downloads folder": "Папка загрузок",
    "Cookies file": "Файл cookies",
    "Cookie files (*.txt)": "Файлы cookies (*.txt)",
    "Output folder": "Папка результата",
    "pass {}/{} · ": "проход {}/{} · ",
    "transcribing ({})…": "транскрибация ({})…",
    "matching…": "сопоставление…",
    "error: {}": "ошибка: {}",
    "No NVIDIA GPU detected, but the device is set to CUDA — processing "
    "will fail. Switch the device to CPU in Settings (slower, but works).":
        "Видеокарта NVIDIA не найдена, а устройство — CUDA: обработка не "
        "сработает. Переключите устройство на CPU в Настройках (медленнее, "
        "но работает).",
    "CPU mode: transcription runs roughly 2-4x slower than on a GPU, but "
    "works everywhere.":
        "Режим CPU: распознавание примерно в 2–4 раза медленнее, чем на "
        "видеокарте, но работает везде.",
    "Open log folder": "Открыть папку журнала",
    "wordmute.log — attach it when reporting a problem.":
        "wordmute.log — приложите его, когда сообщаете о проблеме.",
    "Diagnostics:": "Диагностика:",
    "restart the app to use the installed updates":
        "перезапустите приложение, чтобы использовать обновления",
    "Cached transcript ignored ({}): {}":
        "Сохранённый транскрипт не использован ({}): {}",
    "older than the media": "старше файла",
    "unreadable": "не читается",
    "WordMute is already running.": "WordMute уже запущен.",
    "Use the open window — a second copy would overwrite its settings.":
        "Используйте открытое окно — вторая копия перезаписала бы его "
        "настройки.",
    # history
    "Copy error": "Копировать ошибку",
    "Processed files will appear here.":
        "Обработанные файлы появятся здесь.",
    # url dialog
    "Members-only sites (e.g. Boosty) may need your cookies "
    "file —": "Для сайтов с подпиской (например, Boosty) может быть "
    "нужен файл cookies —",
    "set it in Settings": "указать в настройках",
    # wizard
    "Show": "Показать",
    "Token:": "Токен:",
    "Stored only on this computer.":
        "Хранится только на этом компьютере.",
    "Paste a token first.": "Сначала вставьте токен.",
    "GigaAM is faster and noticeably more accurate for pure Russian "
    "speech, but its long-audio pipeline uses a <i>gated</i> model on "
    "Hugging Face — each user must accept its terms with their own free "
    "account. Three steps, needed once:":
        "GigaAM быстрее и заметно точнее для чисто русской речи, но его "
        "конвейер использует <i>закрытую</i> модель на Hugging Face — "
        "каждый пользователь принимает ее условия со своим бесплатным "
        "аккаунтом. Три шага, нужны один раз:",
    "Create a free Hugging Face account":
        "Создайте бесплатный аккаунт Hugging Face",
    " (skip if you have one)": " (пропустите, если уже есть)",
    "Open the pyannote/segmentation-3.0 page":
        "Откройте страницу pyannote/segmentation-3.0",
    " and fill in the short access form":
        " и заполните короткую форму доступа",
    "Create an access token": "Создайте токен доступа",
    " (type: <b>read</b>) and paste it below":
        " (тип: <b>read</b>) и вставьте его ниже",
    "GigaAM also needs FFmpeg's <i>shared</i> build (separate "
    "from the normal ffmpeg). Install it with "
    "<code>winget install Gyan.FFmpeg.Shared</code>, "
    "then click Re-check.":
        "GigaAM также нужна <i>shared</i>-сборка FFmpeg (отдельно от "
        "обычного ffmpeg). Установите ее командой "
        "<code>winget install Gyan.FFmpeg.Shared</code> и нажмите "
        "«Перепроверить».",
    "Checking token and model access…":
        "Проверка токена и доступа к модели…",
    "✓ Signed in as {}; pyannote access confirmed. Token "
    "saved — GigaAM passes are ready to use.":
        "✓ Вход выполнен как {}; доступ к pyannote подтвержден. Токен "
        "сохранен — проходы GigaAM готовы к работе.",
    # time units / progress
    "h": "ч",
    "min": "мин",
    "s": "с",
    "~{} left": "~осталось {}",
    "transcribing": "транскрибация",
    "downloading": "загрузка",
    "downloading…": "загрузка…",
    "Transcribing… {} of audio processed":
        "Транскрибация… обработано {} аудио",
    "Downloading {}…": "Загрузка {}…",
    "Processing {}…": "Обработка {}…",
    "Finished: {}/{} file(s) ok.": "Готово: {}/{} файл(ов) успешно.",
    "Watching {} — new media files are queued and processed "
    "automatically.":
        "Слежение за {} — новые файлы добавляются и обрабатываются "
        "автоматически.",
    # message boxes
    "Add some files first.": "Сначала добавьте файлы.",
    "Everything in the queue is already processed — add new files "
    "or use Retry on a failed one.":
        "Все в очереди уже обработано — добавьте новые файлы или "
        "нажмите «Повторить» на неудавшемся.",
    "Select at least one word list.":
        "Выберите хотя бы один список слов.",
    "Add at least one pass to the plan.":
        "Добавьте хотя бы один проход в план.",
    "The plan includes GigaAM passes, but the one-time "
    "Hugging Face setup hasn't been completed — they will "
    "likely fail.\n\nOpen the setup wizard now? (Choose No "
    "to try running anyway, e.g. if the models are already "
    "cached.)":
        "В плане есть проходы GigaAM, но разовая настройка Hugging Face "
        "не завершена — они, скорее всего, не сработают.\n\nОткрыть "
        "мастер настройки? (Нажмите «Нет», чтобы все равно попробовать, "
        "например если модели уже скачаны.)",
    "Processing is still running. Cancel and quit?":
        "Обработка еще идет. Отменить и выйти?",
    "No review data for this row yet — it appears after "
    "the file has been processed and something was muted.":
        "Для этой строки пока нет данных проверки — они появляются "
        "после обработки файла, если что-то было заглушено.",
    # url dialog
    "Add URL": "Добавить ссылку",
    "Fetch formats": "Получить форматы",
    "Add (best quality)": "Добавить (лучшее качество)",
    "Add selected": "Добавить выбранное",
    "Best video+audio (recommended)":
        "Лучшее видео+аудио (рекомендуется)",
    "Best video+audio\n(recommended)":
        "Лучшее видео+аудио\n(рекомендуется)",
    "Paste a video URL — the format list loads automatically.":
        "Вставьте ссылку на видео — список форматов загрузится "
        "автоматически.",
    "Fetching format list…": "Получение списка форматов…",
    "Could not fetch formats: {}": "Не удалось получить форматы: {}",
    "Quality": "Качество",
    "Ext": "Формат",
    "Type": "Тип",
    "Note": "Примечание",
    "video+audio": "видео+аудио",
    "video only": "только видео",
    "audio only": "только аудио",
    # review dialog
    "Review": "Проверка",
    "Source": "Источник",
    "⚠ The original file was moved or deleted — playback and "
    "re-rendering are unavailable.":
        "⚠ Исходный файл перемещен или удален — прослушивание и "
        "пересборка недоступны.",
    "Click a row to hear the original audio around it. Uncheck "
    "intervals that should not be muted, then Re-render.":
        "Кликните строку, чтобы услышать оригинал вокруг нее. Снимите "
        "галочки с лишних интервалов и нажмите «Пересобрать».",
    "{} interval(s)": "Интервалов: {}",
    " — {} will be un-muted on re-render":
        " — {} будет раззаглушено при пересборке",
    "Re-rendering…": "Пересборка…",
    "Output updated: {} interval(s) muted.":
        "Результат обновлен: заглушено интервалов: {}.",
    "Re-render failed: {}": "Пересборка не удалась: {}",
    "Playback failed: {}": "Не удалось воспроизвести: {}",
    "You changed the mute selection but didn't re-render, so the "
    "output file is unchanged. Close anyway?":
        "Вы изменили выбор, но не пересобрали результат — файл не "
        "изменился. Все равно закрыть?",
    # models tab
    "Model": "Модель",
    "Size": "Размер",
    "downloaded ✓": "скачана ✓",
    "not downloaded": "не скачана",
    "Delete GigaAM caches": "Удалить кэши GigaAM",
    "No NVIDIA GPU detected — use CPU mode in Settings (roughly "
    "2-4x slower).":
        "GPU NVIDIA не найден — используйте режим CPU в настройках "
        "(примерно в 2-4 раза медленнее).",
    "{} cached (models download automatically on first use).":
        "в кэше {} (модели скачиваются автоматически при первом "
        "использовании).",
    "nothing cached yet — models download automatically on first "
    "use.":
        "кэш пуст — модели скачиваются автоматически при первом "
        "использовании.",
    "Downloading {}… (this can take a while; the app stays usable)":
        "Скачивание {}… (может занять время; приложение остается "
        "рабочим)",
    "Delete the downloaded '{}' model? It will be re-downloaded "
    "automatically the next time it's used.":
        "Удалить скачанную модель «{}»? Она будет скачана заново при "
        "следующем использовании.",
    "Delete all GigaAM model caches? They will be re-downloaded "
    "on the next GigaAM pass.":
        "Удалить все кэши моделей GigaAM? Они будут скачаны заново при "
        "следующем проходе GigaAM.",
    # component setup (slim installer)
    "WordMute components": "Компоненты WordMute",
    "WordMute needs a few components that are downloaded once "
    "(they are not inside the installer to keep it small). "
    "Requirements: a stable internet connection and enough free "
    "disk space. In Russia, python.org / PyPI / Hugging Face may "
    "be blocked or throttled — a VPN may be required.":
        "WordMute нужно несколько компонентов, которые скачиваются один "
        "раз (они не входят в установщик, чтобы он был маленьким). "
        "Потребуются: стабильный интернет и свободное место на диске. "
        "В России python.org / PyPI / Hugging Face могут быть "
        "заблокированы или замедлены — может понадобиться VPN.",
    "Whisper speech recognition (required)":
        "Распознавание речи Whisper (обязательно)",
    "GPU (NVIDIA) — fast, ~1.6 GB download":
        "GPU (NVIDIA) — быстро, загрузка ~1.6 ГБ",
    "CPU only — slower, ~0.3 GB download":
        "Только CPU — медленнее, загрузка ~0.3 ГБ",
    "Video downloads (yt-dlp) — ~10 MB":
        "Загрузка видео (yt-dlp) — ~10 МБ",
    "ffmpeg (audio/video processing) — ~80 MB":
        "ffmpeg (обработка аудио/видео) — ~80 МБ",
    "GigaAM — better Russian recognition (experimental, "
    "~60 MB + ~850 MB model on first use, no account needed)":
        "GigaAM — лучше распознаёт русскую речь (экспериментально, "
        "~60 МБ + модель ~850 МБ при первом использовании, "
        "аккаунт не нужен)",
    "Everything is installed under your user "
    "folder; nothing needs administrator rights.":
        "Все ставится в вашу пользовательскую папку; права "
        "администратора не нужны.",
    "Install": "Установить",
    "Continue": "Продолжить",
    "Installing: {}": "Установка: {}",
    "Python runtime": "Среда Python",
    "Packages": "Пакеты",
    "Done — components installed.": "Готово — компоненты установлены.",
    "Setup failed: {}": "Установка не удалась: {}",
    "Components…": "Компоненты…",
    "Install, repair or add engine components (the slim "
    "installer downloads them on demand).":
        "Установить, починить или добавить компоненты движков (тонкий "
        "установщик скачивает их по мере надобности).",
    "Repair components": "Починить компоненты",
    "Deletes the downloaded components and runs the setup "
    "again — the standard clean retry when something is "
    "broken. Word lists, settings and models are kept.":
        "Удаляет скачанные компоненты и запускает установку заново — "
        "стандартный способ починки, когда что-то сломалось. Списки "
        "слов, настройки и модели сохраняются.",
    "Delete the downloaded components and install them "
    "again? Word lists, settings and models are not "
    "affected. Best done right after starting the app, "
    "before any processing.":
        "Удалить скачанные компоненты и установить их заново? Списки "
        "слов, настройки и модели не затрагиваются. Лучше делать сразу "
        "после запуска приложения, до первой обработки.",
    "Restart the app to use the reinstalled components.":
        "Перезапустите приложение, чтобы использовать переустановленные "
        "компоненты.",
    "Disk usage: components {} · Whisper models {} · "
    "GigaAM {} · total {}":
        "Занято на диске: компоненты {} · модели Whisper {} · "
        "GigaAM {} · всего {}",
    # updates
    "Updates": "Обновления",
    "Check for updates": "Проверить обновления",
    "Update all": "Обновить все",
    "Checking for updates…": "Проверка обновлений…",
    "Updating…": "Обновление…",
    "not installed": "не установлен",
    "could not check": "не удалось проверить",
    "whisper {}: new model revision available":
        "whisper {}: доступна новая версия модели",
    "GigaAM weights update together with the gigaam package.":
        "Веса GigaAM обновляются вместе с пакетом gigaam.",
    "WordMute {} → {} — download: {}":
        "WordMute {} → {} — скачать: {}",
    # add-url batch mode
    "{} links · quality: {}": "Ссылок: {} · качество: {}",
    "Add {} links": "Добавить ссылок: {}",
    "Quality for all links:": "Качество для всех ссылок:",
    "best quality": "лучшее качество",
    "up to 2160p (4K)": "до 2160p (4K)",
    "up to 1440p": "до 1440p",
    "up to 1080p": "до 1080p",
    "up to 720p": "до 720p",
    "up to 480p": "до 480p",
    "audio only (smallest)": "только аудио (самое лёгкое)",
    # setup wizard (8 steps)
    "component setup": "установка компонентов",
    "first-run setup": "первичная настройка",
    "Let's get WordMute ready": "Подготовим WordMute к работе",
    "downloaded once": "скачивается один раз",
    "engine and model": "движок и модель",
    "In Russia python.org, PyPI and Hugging Face may be blocked or "
    "throttled. If a download stalls — turn on a VPN and press "
    "«Retry».":
        "В России python.org, PyPI и Hugging Face могут быть "
        "заблокированы или замедлены. Если загрузка не идёт — "
        "включите VPN и нажмите «Повторить».",
    "Check before installing": "Проверьте перед установкой",
    "Everything here can be changed later in Settings → Components.":
        "Позже всё это можно изменить в Настройках → Компоненты.",
    "Downloading now": "Скачиваем сейчас",
    "Nothing is downloaded later — the app is ready right after setup.":
        "Ничего не докачивается позже — приложение готово сразу "
        "после установки.",
    "Free on disk: {}": "Свободно на диске: {}",
    "Folder": "Папка",
    "runtime environment": "среда исполнения",
    "downloads by link": "загрузка по ссылке",
    "audio and video": "обработка аудио и видео",
    "Russian speech": "русская речь",
    "Installation log": "Журнал установки",
    "A second engine from Sber that reads Russian speech more "
    "accurately than Whisper. Runs fast even without a "
    "graphics card, and needs no accounts or tokens.":
        "Второй движок от Сбера: разбирает русскую речь точнее, чем "
        "Whisper. Быстро работает даже без видеокарты, аккаунты и "
        "токены не нужны.",
    "Works together with Whisper: a typical plan is "
    "GigaAM ×2 → Whisper.":
        "Работает вместе с Whisper: типичный план — "
        "GigaAM ×2 → Whisper.",
    "What you need": "Что понадобится",
    "Review": "Проверка",
    "Installing": "Установка",
    "Step {} of {}": "Шаг {} из {}",
    "{} left": "осталось {}",
    "last step": "последний шаг",
    "Next": "Далее",
    "Back": "Назад",
    "Abort": "Прервать",
    "Start working": "Начать работу",
    "required": "обязательно",
    "optional": "по желанию",
    "GB": "ГБ",
    "MB": "МБ",
    "kB": "КБ",
    "MB/s": "МБ/с",
    "kB/s": "КБ/с",
    "today {}": "сегодня {}",
    "yesterday {}": "вчера {}",
    "ms": "мс",
    "Hz": "Гц",
    "Install": "Установить",
    "WordMute installs the app itself; the recognition engines "
    "are downloaded once, right now. Everything lands in your "
    "user folder — no administrator rights needed.":
        "Само приложение уже установлено; движки распознавания "
        "скачиваются один раз — сейчас. Всё попадает в вашу "
        "пользовательскую папку, права администратора не нужны.",
    "A stable internet connection and free disk space.":
        "Стабильный интернет и свободное место на диске.",
    "Next: one step per component — what it is, how big it "
    "is, whether you need it.":
        "Дальше — по одному шагу на компонент: что это, сколько "
        "весит, нужен ли он вам.",
    "Required components are marked; optional ones can be "
    "skipped and added later in Settings.":
        "Обязательные компоненты отмечены; необязательные можно "
        "пропустить и добавить позже в Настройках.",
    "A stable connection and free disk space are needed. "
    "Setup can be interrupted and resumed later.":
        "Нужен стабильный интернет и свободное место на диске. "
        "Настройку можно прервать и продолжить позже.",
    "In Russia python.org / PyPI / Hugging Face may be "
    "blocked or throttled — turn on a VPN for the setup.":
        "В России python.org / PyPI / Hugging Face могут быть "
        "заблокированы или замедлены — включите VPN на время "
        "установки.",
    "The download can be interrupted and resumed: already "
    "downloaded parts are kept.":
        "Загрузку можно прервать и продолжить позже: уже скачанное "
        "сохраняется.",
    "After this setup the app works fully offline — nothing "
    "downloads mid-video.":
        "После установки приложение работает полностью офлайн — "
        "ничего не докачивается во время обработки.",
    "Python runtime": "Python-окружение",
    "Isolated interpreter for the engines":
        "Отдельный интерпретатор для движков",
    "An embeddable Python build plus pip, installed only for "
    "WordMute. Your system Python (if any) is not touched.":
        "Компактная сборка Python и pip только для WordMute. "
        "Системный Python (если он есть) не затрагивается.",
    "Already installed — this step will be skipped.":
        "Уже установлено — этот шаг будет пропущен.",
    "Speech recognition engine": "Движок распознавания речи",
    "faster-whisper handles any language and runs right after "
    "setup. Pick how it should run and which model to fetch.":
        "faster-whisper понимает любые языки и работает сразу после "
        "установки. Выберите, как его запускать и какую модель "
        "скачать.",
    "Device": "Устройство",
    "GPU (NVIDIA)": "Видеокарта NVIDIA",
    "CPU only": "Только процессор",
    "Fast. Requires an NVIDIA card ({} download).":
        "Быстро. Нужна видеокарта NVIDIA (загрузка {}).",
    "Works everywhere, slower ({} download).":
        "Работает везде, медленнее (загрузка {}).",
    "No NVIDIA GPU detected — CPU is preselected.":
        "Видеокарта NVIDIA не найдена — выбран процессор.",
    "Recognition model": "Модель распознавания",
    "Downloaded during this setup, so the first video starts "
    "immediately.":
        "Скачивается сейчас, поэтому первое видео начнётся сразу.",
    "best quality": "лучшее качество",
    "almost large-v3, much faster": "почти как large-v3, быстрее",
    "good compromise": "хороший компромисс",
    "fastest, lower accuracy": "самая быстрая, точность ниже",
    "Recognition model {}": "Модель распознавания {}",
    "Download videos by link": "Загрузка видео по ссылке",
    "Lets you paste a link (YouTube, VK, rutube, Boosty…) "
    "instead of picking a local file. Tiny download.":
        "Позволяет вставить ссылку (YouTube, VK, rutube, Boosty…) "
        "вместо выбора файла на диске. Занимает совсем мало места.",
    "Install yt-dlp": "Установить yt-dlp",
    "Without it, only local files can be processed.":
        "Без него можно обрабатывать только файлы с диска.",
    "Audio and video processing": "Обработка аудио и видео",
    "Does the actual muting and audio extraction. WordMute "
    "cannot process anything without it.":
        "Именно он заглушает слова и извлекает звук. Без него "
        "WordMute не сможет обработать ни одного файла.",
    "Install ffmpeg": "Установить ffmpeg",
    "Required — muting is impossible without ffmpeg.":
        "Обязательный компонент — без ffmpeg заглушение невозможно.",
    "Extracts audio for recognition and writes the muted "
    "file back.":
        "Извлекает звук для распознавания и собирает обратно файл "
        "с заглушками.",
    "Also makes the thumbnails in the queue.":
        "Также делает миниатюры файлов в очереди.",
    "Installed automatically — it cannot be skipped.":
        "Устанавливается автоматически — пропустить нельзя.",
    "Better Russian recognition": "Точнее для русской речи",
    "An optional second engine that is noticeably more "
    "accurate on Russian speech. Runs fast even without a "
    "graphics card and needs no accounts.":
        "Необязательный второй движок, заметно точнее на русской "
        "речи. Быстро работает даже без видеокарты, аккаунты не "
        "нужны.",
    "Engine and model are downloaded now — nothing is left "
    "for the first video.":
        "Движок и модель скачиваются сейчас — на первое видео "
        "ничего не остаётся.",
    "Experimental: use it together with Whisper, not "
    "instead of it.":
        "Экспериментально: используйте вместе с Whisper, а не "
        "вместо него.",
    "Install GigaAM": "Установить GigaAM",
    "{} including the model": "{} вместе с моделью",
    "What will be downloaded now": "Что будет скачано сейчас",
    "Total download: {}": "Всего к загрузке: {}",
    "Install folder: {}": "Папка установки: {}",
    "skipped": "пропущено",
    "waiting": "ожидает",
    "downloading…": "скачивание…",
    "done": "готово",
    "failed": "ошибка",
    "Do not close the window.": "Не закрывайте окно.",
    "Details": "Подробности",
    "Done — everything is installed and ready.":
        "Готово — всё установлено и готово к работе.",
    "Stop the installation? Downloaded parts are kept and setup "
    "resumes next time.":
        "Остановить установку? Уже скачанное сохранится, установка "
        "продолжится в следующий раз.",
    # setup dialog: model-size choice
    "Recognition model (downloads on first use; "
    "changeable later in Settings):":
        "Модель распознавания (скачается при первой обработке; "
        "можно поменять позже в Настройках):",
    "large-v3 — best quality, ~3 GB":
        "large-v3 — лучшее качество, ~3 ГБ",
    "large-v3-turbo — near large-v3 quality, much faster, ~1.6 GB":
        "large-v3-turbo — почти как large-v3, заметно быстрее, ~1,6 ГБ",
    "medium — good compromise, ~1.5 GB":
        "medium — хороший компромисс, ~1,5 ГБ",
    "small — fastest, lowest accuracy, ~0.5 GB":
        "small — самая быстрая, точность ниже, ~0,5 ГБ",
    "New WordMute version available: {} (you have {})":
        "Доступна новая версия WordMute: {} (у вас {})",
    "Click to open the download page.":
        "Нажмите, чтобы открыть страницу загрузки.",
    "Updates installed.": "Обновления установлены.",
    "Restart the app to use them.":
        "Перезапустите приложение, чтобы они заработали.",
    "Update failed: {}": "Обновление не удалось: {}",
    # history tab
    "Time": "Время",
    "Muted": "Заглушено",
    "Plan": "План",
    "Output": "Результат",
    "{} record(s)": "Записей: {}",
    "Clear the whole processing history?":
        "Очистить всю историю обработки?",
    "Open results folder": "Открыть папку результатов",
    "downloaded this month: {}": "скачано за месяц: {}",
    "muting": "заглушение",
    "Re-render finished": "Пересборка завершена",
    "Processing language": "Язык обработки",
    "Auto (main setup)": "Авто (общие настройки)",
    "Save SRT": "Сохранить SRT",
    "Export the muted words with their timestamps as an "
    ".srt subtitle file.":
        "Сохранить заглушенные слова с таймкодами в файл "
        "субтитров .srt.",
    "Subtitles (*.srt)": "Субтитры (*.srt)",
    "SRT saved: {} ({} entries)": "SRT сохранён: {} (записей: {})",
    "Save failed: {}": "Не удалось сохранить: {}",
    "from cache": "из кэша",
    "total": "итого",
    "Videos downloaded by link this calendar month — handy "
    "for metered/VPN connections. Component and model "
    "downloads are not included.":
        "Видео, загруженные по ссылкам в этом календарном месяце — "
        "полезно при лимитном трафике или VPN. Загрузки компонентов "
        "и моделей не учитываются.",
    "Done": "Готово",
    "Error": "Ошибка",
    # file cleanup (queue ⋮ menu + history right-click)
    "Delete source video and JSONs":
        "Удалить исходник и JSON-файлы",
    "Delete all files (source, clean, JSONs)":
        "Удалить все файлы (исходник, результат, JSON)",
    "Move {} file(s) to the Recycle Bin?":
        "Переместить в Корзину файлов: {}?",
    "Delete failed: {}": "Не удалось удалить: {}",
    "files deleted": "файлы удалены",
    "downloaded · waiting": "скачано · ожидает",
    "Files on disk": "Файлы на диске",
    "Files deleted": "Файлы удалены",
    "Source deleted": "Исходник удалён",
    "Output deleted": "Результат удалён",
    # transcript tab
    "Text": "Текст",
    "{} words": "Слов: {}",
    "{} of {} blocks": "{} из {} блоков",
    # word lists tab
    "{} entries": "Записей: {}",
    "Saved: {} entries": "Сохранено: {} записей",
    " ({} duplicate(s) merged)": " (объединено дубликатов: {})",
    "слово = exact ·  корень* = word starts with ·  "
    "*корень* = anywhere in word ·  слово слово = phrase ·  "
    "# comment":
        "слово = точное совпадение ·  корень* = слово начинается с ·  "
        "*корень* = в любом месте слова ·  слово слово = фраза ·  "
        "# комментарий",
    # tooltips
    "Open a review file (saved next to each processed output) "
    "to listen to muted moments and un-mute false positives.":
        "Откройте файл проверки (сохраняется рядом с каждым результатом), "
        "чтобы прослушать заглушенные места и раззаглушить ложные "
        "срабатывания.",
    "One-time Hugging Face setup required for GigaAM passes. "
    "Whisper works without any of this.":
        "Разовая настройка Hugging Face, нужная для проходов GigaAM. "
        "Whisper работает без нее.",
    "Automatically queue and process new media files appearing "
    "in a chosen folder.":
        "Автоматически добавлять и обрабатывать новые файлы, появляющиеся "
        "в выбранной папке.",
    "Run every pass even if an earlier one finds nothing; the "
    "final pass re-transcribes completely fresh, ignoring "
    "caches.":
        "Выполнять все проходы, даже если ранний ничего не нашел; "
        "последний проход транскрибирует заново, игнорируя кэш.",
    "Re-transcribe from scratch on the first pass (one-off; "
    "not remembered).":
        "Транскрибировать с нуля на первом проходе (разово; не "
        "запоминается).",
    "Whisper language code (e.g. ru, en); ignored by GigaAM "
    "passes.":
        "Код языка Whisper (например, ru, en); проходы GigaAM его "
        "игнорируют.",
    "Fast Whisper mode (experimental)":
        "Быстрый режим Whisper (эксперимент)",
    "Batched decoding: 2-4x faster transcription, but a "
    "slightly higher chance of missed words and about twice "
    "the RAM on CPU. Requires voice activity detection.":
        "Пакетное распознавание: в 2–4 раза быстрее, но чуть выше "
        "шанс пропустить слово и примерно вдвое больше памяти на CPU. "
        "Требует включённого VAD.",
    "Disable if words at clip edges are missed.":
        "Отключите, если пропускаются слова на краях записи.",
    "Extra silence around each muted word; never bleeds into "
    "neighboring words.":
        "Дополнительная тишина вокруг каждого заглушенного слова; "
        "никогда не задевает соседние слова.",
    "Replace muted words with a beep tone instead of silence. "
    "Note: files with several audio tracks keep only the "
    "first one in beep mode.":
        "Заменять заглушенные слова писком вместо тишины. Замечание: у "
        "файлов с несколькими аудиодорожками в режиме писка остается "
        "только первая.",
    "Cookie file in Netscape format (as exported by yt-dlp or "
    "a browser extension).":
        "Файл cookies в формате Netscape (как экспортируют yt-dlp или "
        "расширения браузера).",
    "Skip the format list and download best video+audio.":
        "Пропустить список форматов и скачать лучшее видео+аудио.",
    # plan widget tips
    "Whisper: handles English and mixed-language speech well; "
    "slower; works out of the box, no extra setup.":
        "Whisper: хорошо работает с английской и смешанной речью; "
        "медленнее; работает сразу, без настройки.",
    "GigaAM: faster and noticeably more accurate for pure Russian "
    "speech; weaker on mixed Russian/English (may mangle English "
    "words); requires a one-time Hugging Face setup.":
        "GigaAM: быстрее и заметно точнее для чисто русской речи; "
        "слабее на смеси русского и английского; требует разовой "
        "настройки Hugging Face.",
    "GigaAM: faster, best for pure Russian.\n"
    "Whisper: slower, handles English/mixed speech.":
        "GigaAM: быстрее, лучше для чисто русской речи.\n"
        "Whisper: медленнее, понимает английскую и смешанную речь.",
    "Passes run top to bottom; each pass re-checks the previous "
    "pass's output and stops early once nothing new is found. "
    "Different engines catch words the other missed.":
        "Проходы идут сверху вниз; каждый перепроверяет результат "
        "предыдущего и останавливается, когда нового ничего не "
        "найдено. Разные движки ловят то, что пропустил другой.",
    # dialogs (shared) — confirmations name the action, never Yes/No
    "Close": "Закрыть",
    "Got it": "Понятно",
    "Save": "Сохранить",
    "Discard": "Не сохранять",
    "They can be restored from the Recycle Bin.":
        "Их можно вернуть из Корзины.",
    "To Recycle Bin": "В Корзину",
    "Delete failed": "Не удалось удалить",
    "Nothing to review yet": "Проверять пока нечего",
    "Review data appears after the file has been processed and "
    "something was muted.":
        "Данные проверки появляются после обработки файла, если "
        "что-то было заглушено.",
    "Could not open the review file":
        "Не удалось открыть файл проверки",
    "Everything is processed already": "Всё уже обработано",
    "Add new files, or use Retry on a failed one.":
        "Добавьте новые файлы или нажмите «Повторить» на неудачном.",
    "Processing is still running.": "Обработка ещё идёт.",
    "Quitting cancels the current file; finished files are kept.":
        "При выходе текущий файл отменяется, готовые остаются.",
    "Cancel and quit": "Отменить и выйти",
    "Delete source and JSONs": "Удалить исходник и JSON",
    "Delete all files": "Удалить все файлы",
    "Clear history": "Очистить историю",
    "Only the list is cleared — no video file is touched.":
        "Очищается только список — сами видео не затрагиваются.",
    "Delete the downloaded '{}' model?":
        "Удалить скачанную модель «{}»?",
    "It is downloaded again the next time it is used.":
        "Она скачается заново при следующем использовании.",
    "Delete model": "Удалить модель",
    "Delete all GigaAM model caches?": "Удалить все кэши моделей GigaAM?",
    "They are downloaded again on the next GigaAM pass.":
        "Они скачаются заново на следующем проходе GigaAM.",
    "Delete caches": "Удалить кэши",
    "Reinstall the downloaded components?":
        "Переустановить скачанные компоненты?",
    "Word lists, settings and models are not affected. Best done right "
    "after starting the app, before any processing.":
        "Списки слов, настройки и модели не затрагиваются. Лучше делать "
        "сразу после запуска, до обработки.",
    "Reinstall": "Переустановить",
    "Close without re-rendering?": "Закрыть без пересборки?",
    "You changed the mute selection but didn't re-render, so the "
    "output file stays as it is.":
        "Вы изменили набор заглушек, но не пересобрали результат — "
        "файл останется прежним.",
    "Close anyway": "Всё равно закрыть",
    "Stop the installation?": "Прервать установку?",
    "Downloaded parts are kept and setup resumes next time.":
        "Скачанное сохранится, установка продолжится в следующий раз.",
    "Stop installing": "Прервать",
    "The word list has unsaved changes.":
        "В списке слов есть несохранённые правки.",
    "Saving also sorts the list and removes duplicates.":
        "При сохранении список сортируется, дубликаты убираются.",
    "Browse…": "Обзор…",
    "Delete": "Удалить",
    "Download": "Скачать",
    "Open folder": "Открыть папку",
    "Clear": "Очистить",
    "Export SRT…": "Экспорт SRT…",
    "Search:": "Поиск:",
    "Word or phrase:": "Слово или фраза:",
    # settings
    "Settings": "Настройки",
    "Whisper model:": "Модель Whisper:",
    "GigaAM model:": "Модель GigaAM:",
    "Device:": "Устройство:",
    "Mute padding:": "Отступ заглушения:",
    "Whisper language:": "Язык Whisper:",
    "Downloads folder:": "Папка загрузок:",
    "Output location:": "Куда сохранять результат:",
    "Next to each input (<name>.clean.<ext>)":
        "Рядом с исходным файлом (<имя>.clean.<расш>)",
    "Into folder:": "В папку:",
    "Voice activity detection (whisper only)":
        "Детекция речи VAD (только whisper)",
    "Beep instead of silence": "Пищать вместо тишины",
    "Beep frequency:": "Частота писка:",
    "Interface language:": "Язык интерфейса:",
    "(takes effect after restart)": "(вступит в силу после перезапуска)",
    # review — the columns need their own keys: plain "Start" is
    # already taken by the run button ("Старт")
    "Mute": "Глушить",
    "Interval start": "Начало",
    "Interval end": "Конец",
    "Words": "Слова",
    "Pass": "Проход",
    "Engine": "Движок",
    "Stop playback": "Остановить звук",
    "Mute all": "Глушить все",
    "Unmute all": "Не глушить ничего",
    "Re-render output": "Пересобрать результат",
}
