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
