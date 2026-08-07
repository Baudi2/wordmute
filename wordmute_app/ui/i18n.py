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


RU = {
    # main window
    "Add Files…": "Добавить файлы…",
    "Add Folder…": "Добавить папку…",
    "Add URL…": "Добавить ссылку…",
    "Remove Selected": "Убрать выбранное",
    "Review…": "Проверка…",
    "Settings…": "Настройки…",
    "GigaAM Setup…": "Настройка GigaAM…",
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
    "Watch Folder…": "Следить за папкой…",
    "Stop Watching": "Перестать следить",
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
    "Paste a video URL, then either fetch the format list or add "
    "it at best quality.":
        "Вставьте ссылку на видео, затем получите список форматов или "
        "добавьте в лучшем качестве.",
    "Fetching format list…": "Получение списка форматов…",
    "Could not fetch formats: {}": "Не удалось получить форматы: {}",
    "Quality": "Качество",
    "Ext": "Формат",
    "Type": "Тип",
    "Note": "Примечание",
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
    # history tab
    "Time": "Время",
    "Muted": "Заглушено",
    "Plan": "План",
    "Output": "Результат",
    "{} record(s)": "Записей: {}",
    "Clear the whole processing history?":
        "Очистить всю историю обработки?",
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
    # dialogs (shared)
    "Close": "Закрыть",
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
    # review
    "Mute": "Глушить",
    "Words": "Слова",
    "Pass": "Проход",
    "Engine": "Движок",
    "Stop playback": "Остановить звук",
    "Mute all": "Глушить все",
    "Unmute all": "Не глушить ничего",
    "Re-render output": "Пересобрать результат",
}
