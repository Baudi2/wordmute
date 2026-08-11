# WordMute — руководство по установке / Installation Guide

> **Пользователю:** если что-то пошло не так — скопируйте ВЕСЬ этот
> файл в любой ИИ-ассистент (ChatGPT, Claude, DeepSeek и т.п.),
> опишите свою проблему, и он поможет пройти установку по шагам.
> Английская часть ниже написана специально для ИИ-помощника.

## Кратко для пользователя

1. Запустите `WordMute-Setup-0.5.0.exe`. Windows покажет предупреждение
   SmartScreen («Система Windows защитила ваш компьютер») — нажмите
   **«Подробнее» → «Выполнить в любом случае»**. Это нормально:
   установщик просто не подписан платным сертификатом.
2. Установщик маленький (~150 МБ) и ставит только само приложение.
   Права администратора НЕ нужны.
3. При первом запуске WordMute откроет окно **«Компоненты»** и скачает
   недостающее: Python-окружение, распознавание речи Whisper, yt-dlp
   (загрузка видео) и ffmpeg. Выберите вариант GPU, если у вас
   видеокарта NVIDIA, иначе CPU. Там же выбирается размер модели
   распознавания: large-v3 (~3 ГБ, лучшее качество), medium (~1,5 ГБ)
   или small (~0,5 ГБ) — сама модель скачается при первой обработке.
4. **Что понадобится:**
   - свободное место: ~1 ГБ (CPU) / ~2.5 ГБ (GPU) для компонентов
     + ~3 ГБ для модели распознавания при первом запуске обработки;
   - стабильный интернет;
   - **в России**: сайты python.org, pypi.org и huggingface.co могут
     быть заблокированы или замедлены — включите VPN на время
     установки и первого запуска.
5. Опциональный компонент **GigaAM** (лучше распознаёт русскую речь,
   ~60 МБ + модель ~850 МБ при первом использовании, аккаунт не
   нужен, экспериментальный) можно доустановить позже: вкладка
   «Модели» → «Компоненты…».

---

## For the AI assistant helping with installation

You are helping a (likely Russian-speaking, non-technical) user
install **WordMute**, a Windows desktop app that mutes unwanted words
in video/audio files using local speech recognition. Everything below
is factual reference about how the installation works. Walk the user
through their specific problem step by step; ask what they see on
screen. Answer in the user's language.

### Architecture facts

- The installer (`WordMute-Setup-0.5.0.exe`, Inno Setup, ~150 MB)
  installs ONLY the application, per-user (no admin rights), default
  location `%LOCALAPPDATA%\Programs\WordMute`. It creates a Start-menu
  entry, an optional desktop icon, and an uninstaller in Windows
  Settings → Apps.
- On first launch the app shows a **component setup dialog** which
  downloads, into `%LOCALAPPDATA%\WordMute\runtime`:
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
     - optional GigaAM via `onnx-asr[cpu,hub]` (~60 MB; the ~850 MB
       model downloads from huggingface.co on first use — CPU
       inference, NO Hugging Face account or token required).
- On the first actual transcription the app additionally downloads
  the Whisper model chosen during setup (`large-v3` ~3 GB default,
  `medium` ~1.5 GB, `small` ~0.5 GB) from `huggingface.co` into
  `%USERPROFILE%\.cache\huggingface`. The model can be changed later
  in Настройки and pre-downloaded in the Модели tab.
- The app checks GitHub for new WordMute versions shortly after
  startup and may show a tray notification offering the download
  page — this is normal behavior, not malware.
- App settings live in `%APPDATA%\WordMute` (settings.json,
  word lists, history, thumbnails).

### Network requirements (critical for users in Russia)

The setup needs these hosts reachable: `python.org`, `pypi.org` and
`files.pythonhosted.org`, `bootstrap.pypa.io`, `gyan.dev`,
`huggingface.co` and `cas-bridge.xethub.hf.co` (model downloads),
plus the video sites the user downloads from. Several of these are
blocked or throttled in Russia — the standard fix is enabling a VPN
for the duration of setup and the first model download. Processing
itself is fully offline afterwards; the VPN is only needed again for
updates or new model downloads.

### Troubleshooting map

| Symptom | Cause | Fix |
|---|---|---|
| "Windows protected your PC" on the installer | Unsigned installer (SmartScreen) | «Подробнее» → «Выполнить в любом случае». The file is safe if obtained from the developer directly. |
| Component setup fails instantly / "getaddrinfo failed" / timeouts | Blocked hosts (common in RU) or no internet | Enable VPN, press «Установить» again — the setup is safe to re-run, it resumes/overwrites cleanly. |
| pip errors mentioning "No space left" / диск | Not enough free disk | Free ~5 GB on drive C: and re-run the component setup. |
| Antivirus deletes/quarantines files during setup | AV false positive on downloaded exes | Add `%LOCALAPPDATA%\WordMute` to AV exclusions, re-run setup. |
| App starts but transcription fails with CUDA/DLL errors | GPU flavor installed without an NVIDIA GPU or with a very old driver | Re-open Модели → «Компоненты…», install the CPU flavor (it overwrites), or update the NVIDIA driver. |
| First transcription stuck at "Загрузка модели" | The ~3 GB model download from huggingface.co is slow/blocked | Wait, or enable VPN; progress is visible in the app log («Подробности»). |
| Video download fails for a specific site | yt-dlp needs updating (sites change constantly) | Модели tab → «Проверить обновления» → «Обновить все», then restart the app. |
| Boosty/member-only videos fail | Cookies needed | Настройки → «Файл cookies»: export cookies from the browser (a "cookies.txt" extension) and select that file. |
| GigaAM errors about Hugging Face token / pyannote | Only affects OLD installs using the legacy torch backend | Current versions run GigaAM via onnx-asr and need no account. If this appears: Модели → «Починить компоненты» to reinstall the current component set. The «Настройка GigaAM» wizard remains only for the legacy path. |
| Everything broken, want a clean retry | — | In the app: Модели → **«Починить компоненты»** — deletes the runtime and reruns the component setup in one click (restart the app afterwards). If the app itself won't start: delete `%LOCALAPPDATA%\WordMute\runtime` manually and launch again — the setup dialog reappears. App settings/word lists are elsewhere and survive. |

### Diagnostics

To produce a machine-readable status report, run in PowerShell:

```
$env:WORDMUTE_RUNTIME_REPORT="$env:USERPROFILE\Desktop\wordmute-report.json"
& "$env:LOCALAPPDATA\Programs\WordMute\WordMute.exe"
```

The JSON on the desktop shows which components are present. `true`
everywhere except possibly `gigaam` = healthy install.

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
