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
