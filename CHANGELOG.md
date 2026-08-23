# Changelog

The installer for each release is on the
[GitHub releases page](https://github.com/Baudi2/wordmute/releases);
the in-app check («Модели → Проверить обновления») compares against it.
The first heading below must match `wordmute_app.__version__`
(tests/test_version.py enforces it).

## 0.7.0 — 2026-08-23

Design rounds 1–4 applied: themed menus and confirmations, the
install page that fits its log, compact batch Add-URL with host chips,
locale dates and unit suffixes, the lighter Word Lists header with a
Ctrl+F find bar and filter mode, the Models tab regroup (one model
list, cancellable downloads, a stacked disk bar, update rows with
«Обновить все (N)»), the native title bar as the header, empty states
as drop targets.

Stability, from a full code audit before this release:

- the silent crash («the window just disappeared», exit 0xC0000409)
  when a worker thread outlived its owner — on «Проверить обновления»,
  on Esc in the Review and Setup dialogs, on closing during a model
  load or a stalled download, on Cancel in the Add-URL dialog — is
  fixed at the root (ui/threads.py) and guarded by tests;
- Cancel during muting no longer leaves ffmpeg running in the
  background with a half-written `.tmp` next to the video;
- an unreachable output folder, same-named inputs in folder mode,
  `.mp3` inputs, the Recycle Bin on network/exFAT drives, the wizard's
  model/device choice being reverted, «Починить компоненты» after a
  transcription — all fixed;
- playlists are refused before a byte is downloaded; a cancelled
  install or model download no longer reads as «installed»; a stale or
  unreadable transcript cache is re-transcribed; settings, word lists
  and review sidecars are written atomically; the cookies file is
  never rewritten; one instance of the app at a time;
- a crash log: `%APPDATA%\WordMute\wordmute.log` (Настройки →
  «Открыть папку журнала»), with Qt messages, Python tracebacks from
  every thread and faulthandler dumps;
- the uninstaller asks whether to delete the downloaded components,
  settings and history (kept by default).

## 0.6.0 — 2026-08-18

Continuous download pump, per-item language profiles («Язык
обработки»), delete-source protection, real names for batch links,
first run follows the OS language, batch quality cap, one link per
line, ffmpeg download retries + GitHub mirror, GigaAM back on the GPU
with torch+CUDA, GigaAM onnx sentence splitting fixed, the 8-step
setup wizard.

## 0.5.0 — 2026-08-12

GigaAM via onnx-asr (no Hugging Face token), toasts, the review
waveform strip, skeleton shimmer on bulk adds, fade-edged mutes, «Save
SRT» in the review dialog, large-v3-turbo, the opt-in fast Whisper
mode.

## 0.4.0 — 2026-08-11

Keep-awake during runs, finish notification, window clamp, «Починить
компоненты», disk usage in Models, monthly traffic stat in History, the
self-update check, model-size choice in setup, background thumbnails
for bulk adds, multi-URL paste.

## 0.3.0 — 2026-08-09

First public release: the slim installer with the app-managed runtime
and the first-run component setup.
