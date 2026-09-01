# WordMute — руководство по установке / Installation Guide

> **Пользователю:** если что-то пошло не так — скопируйте ВЕСЬ этот
> файл в любой ИИ-ассистент (ChatGPT, Claude, DeepSeek и т.п.),
> опишите свою проблему, и он поможет пройти установку по шагам.
> Английская часть ниже написана специально для ИИ-помощника.

## Кратко для пользователя

1. Запустите `WordMute-Setup-0.7.1.exe`. Windows покажет предупреждение
   SmartScreen («Система Windows защитила ваш компьютер») — нажмите
   **«Подробнее» → «Выполнить в любом случае»**. Это нормально:
   установщик просто не подписан платным сертификатом.
2. Установщик маленький (~160 МБ) и ставит только само приложение.
   Права администратора НЕ нужны.
3. При первом запуске WordMute откроет **мастер настройки** из 8 шагов
   и объяснит каждый компонент: Python-окружение, распознавание речи
   Whisper (выбор GPU/CPU и размер модели: large-v3 ~3 ГБ — лучшее
   качество, large-v3-turbo ~1,5 ГБ, medium ~1,5 ГБ, small ~0,5 ГБ),
   yt-dlp (загрузка видео по ссылкам), ffmpeg (обязателен) и
   опциональный GigaAM. Предпоследний шаг показывает итоговый размер
   загрузки, последний — ход установки.
   **Всё скачивается сразу во время настройки** — после неё программа
   готова к работе, первое видео не тянет ничего дополнительно.
4. **Что понадобится:**
   - свободное место: ~1 ГБ (CPU) / ~2,5 ГБ (GPU) для компонентов
     + модель распознавания (0,5–3 ГБ по выбору)
     + ~0,9 ГБ, если оставить GigaAM;
   - стабильный интернет;
   - **в России**: сайты python.org, pypi.org и huggingface.co могут
     быть заблокированы или замедлены — включите VPN на время
     установки.
5. **GigaAM** (движок Сбера, точнее распознаёт русскую речь; ~60 МБ
   движок + ~850 МБ модель, аккаунт и токен не нужны) отмечен в
   мастере галочкой по умолчанию. Если снять её, его можно
   доустановить позже: вкладка «Модели» → «Компоненты…».
6. **Если что-то пошло не так:** приложение ведёт журнал
   `%APPDATA%\WordMute\wordmute.log` (Настройки → «Открыть папку
   журнала») — приложите его к сообщению о проблеме.
7. **Удаление:** деинсталлятор спросит, удалять ли загруженные
   компоненты, настройки, списки слов и историю (по умолчанию —
   оставить). Модели распознавания в `%USERPROFILE%\.cache\huggingface`
   остаются в любом случае — удалите папку вручную, если они больше не
   нужны.

---

## For the AI assistant helping with installation

You are helping a (likely Russian-speaking, non-technical) user
install **WordMute**, a Windows desktop app that mutes unwanted words
in video/audio files using local speech recognition. Everything below
is factual reference about how the installation works. Walk the user
through their specific problem step by step; ask what they see on
screen. Answer in the user's language.

### Architecture facts

- The installer (`WordMute-Setup-0.7.1.exe`, Inno Setup, ~160 MB)
  installs ONLY the application, per-user (no admin rights), default
  location `%LOCALAPPDATA%\Programs\WordMute`. It creates a Start-menu
  entry, an optional desktop icon, and an uninstaller in Windows
  Settings → Apps.
- On first launch the app shows an **8-step setup wizard** (intro →
  Python → Whisper → yt-dlp → ffmpeg → GigaAM → review → installing).
  It follows the Windows display language on that first run and
  downloads EVERYTHING the user selected before finishing — nothing is
  deferred to the first video. It writes into
  `%LOCALAPPDATA%\WordMute\runtime`:
  1. **Python runtime**: embeddable CPython 3.12 from
     `python.org/ftp/python/...` (~11 MB) + pip from
     `bootstrap.pypa.io/get-pip.py`;
  2. **ffmpeg**: `gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip`
     (~80 MB), extracted to `runtime\ffmpeg`;
  3. **pip packages** from pypi.org into
     `runtime\python\Lib\site-packages`:
     - Whisper GPU flavor: `faster-whisper`, `nvidia-cublas-cu12`,
       `nvidia-cudnn-cu12` (~1.6 GB) — needs an NVIDIA GPU with a
       normal driver, nothing else;
     - Whisper CPU flavor: `faster-whisper` only (~0.3 GB);
     - `yt-dlp` (~10 MB);
     - optional GigaAM via `onnx-asr[cpu,hub]` (~60 MB) — CPU
       inference, NO Hugging Face account or token required;
  4. **models**, from `huggingface.co` into
     `%USERPROFILE%\.cache\huggingface`: the chosen Whisper model
     (`large-v3` ~3 GB default, `large-v3-turbo` / `medium` ~1.5 GB,
     `small` ~0.5 GB) and, when GigaAM is kept, its ~850 MB ONNX model
     plus the silero VAD. The Whisper model can be changed later in
     Настройки; other sizes can be pre-downloaded in the Модели tab.
- The app checks GitHub for new WordMute versions shortly after
  startup and may show a tray notification offering the download
  page — this is normal behavior, not malware.
- App settings live in `%APPDATA%\WordMute` (settings.json,
  word lists, history, thumbnails).

### Network requirements (critical for users in Russia)

The setup needs these hosts reachable: `python.org`, `pypi.org` and
`files.pythonhosted.org`, `bootstrap.pypa.io`, `gyan.dev`,
`huggingface.co` and `cas-bridge.xethub.hf.co` (model downloads),
`github.com` (ffmpeg mirror + update check), plus the video sites the
user downloads from. Several of these are blocked or throttled in
Russia — the standard fix is enabling a VPN for the duration of the
setup wizard, which is where every download now happens. Processing
itself is fully offline afterwards; the VPN is only needed again for
updates or extra model downloads.

### Troubleshooting map

| Symptom | Cause | Fix |
|---|---|---|
| "Windows protected your PC" on the installer | Unsigned installer (SmartScreen) | «Подробнее» → «Выполнить в любом случае». The file is safe if obtained from the developer directly. |
| Component setup fails instantly / "getaddrinfo failed" / timeouts | Blocked hosts (common in RU) or no internet | Enable VPN, press «Установить» again — the setup is safe to re-run, it resumes/overwrites cleanly. |
| pip errors mentioning "No space left" / диск | Not enough free disk | Free ~5 GB on drive C: and re-run the component setup. |
| Antivirus deletes/quarantines files during setup | AV false positive on downloaded exes | Add `%LOCALAPPDATA%\WordMute` to AV exclusions, re-run setup. |
| App starts but transcription fails with CUDA/DLL errors | GPU flavor installed without an NVIDIA GPU or with a very old driver | Re-open Модели → «Компоненты…», install the CPU flavor (it overwrites), or update the NVIDIA driver. |
| Setup sits on «Модель распознавания» for a long time | That step downloads the whole ~3 GB Whisper model (and ~850 MB for GigaAM) from huggingface.co — slow or throttled links make it look stuck | Wait, or enable VPN and press «Установить» again; the per-component progress and the «Журнал установки» show what is happening. |
| ffmpeg step fails with a timeout | gyan.dev is unreachable | Nothing to do: the app retries and falls back to a GitHub mirror on its own; if both fail, enable VPN and re-run the setup. |
| Video download fails for a specific site | yt-dlp needs updating (sites change constantly) | Модели tab → «Проверить обновления» → «Обновить все», then restart the app. |
| Boosty/member-only videos fail | Cookies needed | Настройки → «Файл cookies»: export cookies from the browser (a "cookies.txt" extension) and select that file. |
| GigaAM errors about Hugging Face token / pyannote | Only possible on an OLD install that still uses the legacy torch backend | Current versions run GigaAM via onnx-asr: no account, no token, and the setup wizard has no token step at all. Fix: Модели → «Починить компоненты» to reinstall the current component set. |
| Everything broken, want a clean retry | — | In the app: Модели → **«Починить компоненты»** — deletes the runtime and reruns the component setup in one click (restart the app afterwards). If the app itself won't start: delete `%LOCALAPPDATA%\WordMute\runtime` manually and launch again — the setup dialog reappears. App settings/word lists are elsewhere and survive. |

### Diagnostics

To produce a machine-readable status report: real users' default
terminal is often cmd, not PowerShell — give them the variant that
matches their window (or the cmd one, it also runs from Win+R).

cmd («Командная строка», black window; also works via Win+R):

```
set "WORDMUTE_RUNTIME_REPORT=%USERPROFILE%\Desktop\wordmute-report.json" && "%LOCALAPPDATA%\Programs\WordMute\WordMute.exe"
```

PowerShell (blue window, prompt starts with `PS`):

```
$env:WORDMUTE_RUNTIME_REPORT="$env:USERPROFILE\Desktop\wordmute-report.json"
& "$env:LOCALAPPDATA\Programs\WordMute\WordMute.exe"
```

The JSON on the desktop shows which components are present. `true`
everywhere except possibly `gigaam` = healthy install.

**Crash log (0.7.0+):** `%APPDATA%\WordMute\wordmute.log` — also
reachable from Настройки → «Открыть папку журнала». It holds the
startup banner with the version, Qt messages, Python tracebacks from
every thread and a faulthandler dump if the process died hard. Ask
for it whenever the user says the window disappeared or a button
«does nothing»; the last lines before a `===` banner are the previous
session's end. Rotated once at ~2 MB (`wordmute.log.1`).

**Uninstall:** the uninstaller removes the program folder and then
asks whether to delete `%LOCALAPPDATA%\WordMute` (components) and
`%APPDATA%\WordMute` (settings, word lists, history, the log); the
default is to keep them. Recognition models under
`%USERPROFILE%\.cache\huggingface` are never touched.

### What NOT to advise

- Do not suggest installing system-wide Python, ffmpeg or CUDA — the
  app manages its own copies; system installs are unnecessary and can
  confuse the setup.
- Do not suggest running the installer as administrator; it is
  per-user by design.
- Do not edit files inside `%LOCALAPPDATA%\Programs\WordMute` — a
  broken app is fixed by reinstalling; a broken runtime by the
  «Починить компоненты» button (or deleting
  `%LOCALAPPDATA%\WordMute\runtime` when the app won't start).
