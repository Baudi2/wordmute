# Licensing / redistribution checklist

Status of every component the distributable build ships or touches.
**Verify each ⚠ item against the current upstream license text before
any public release** — this file records the plan, not legal advice.

## Bundled in the installer (v1, whisper-only build)

| Component | License | Redistribution notes |
|---|---|---|
| Python runtime (frozen by PyInstaller) | PSF | Redistribution fine; keep license text. |
| PyInstaller bootloader | GPL with linking exception | Exception explicitly allows distributing frozen apps under any license. |
| PySide6 / Qt 6 | LGPL-3.0 | OK as shipped: Qt is dynamically linked (separate DLLs, relinkable). Ship LGPL text; don't statically link. |
| faster-whisper | MIT | OK. |
| CTranslate2 | MIT | OK. |
| onnxruntime | MIT | OK. |
| PyAV (av) | BSD-3 | Wheels embed FFmpeg libraries → FFmpeg licensing applies (LGPL build per PyAV docs). ⚠ confirm wheel build flags. |
| tokenizers / huggingface_hub | Apache-2.0 | OK. |
| yt-dlp | Unlicense | OK. Separate issue: some sites' ToS restrict downloading — document for users; the app downloads only URLs the user pastes. |
| NVIDIA cuBLAS / cuDNN (pip wheels) | NVIDIA proprietary, redistributable | CUDA EULA / cuDNN license allow redistribution of runtime libraries with applications. ⚠ re-read current EULA §attachments before release; keep NVIDIA license text in the installer. |
| ffmpeg.exe / ffprobe.exe (Gyan **full/static** build) | **GPL-3.0** | Redistributable, but GPL obliges: include GPL text + written offer/link to the exact corresponding source (gyan.dev publishes it). Alternative: make the installer download ffmpeg at first run instead of bundling. ⚠ decide before release. |
| Word lists (RU/EN) | Project's own content | Author's curated lists, shipped as editable templates. |
| App icon | Generated in-repo | Ours. |

## Downloaded at runtime onto the user's machine (never redistributed by us)

| Component | License | Notes |
|---|---|---|
| Whisper model weights (Systran/faster-whisper-*) | MIT | Downloaded from HF by the app (model manager / first use). |
| GigaAM models | MIT (code); weights per Sber's repo terms | ⚠ verify weight license on the exact model revisions used. Runtime download only. |
| pyannote/segmentation-3.0 | MIT code; **gated weights** | Cannot be bundled at all: each user accepts terms with their own HF account (the app's GigaAM wizard walks through this). |

## Not in the v1 installer (documented gap)

torch (BSD-3), GigaAM, pyannote.audio (MIT), torchcodec, FFmpeg
*shared* build — the GigaAM stack. v1 ships whisper-only; GigaAM works
in a developer environment (repo + pip). v2 options, in preference
order:
1. Installer-time optional download ("GigaAM support" component) that
   pip-installs the stack into an app-managed venv.
2. Separate "WordMute Full" installer (~6-7 GB) with torch CUDA frozen.

## Release checklist

- [ ] Bundle third-party license texts into the installer
      (`{app}\licenses\`), incl. LGPL-3.0 (Qt), GPL-3.0 + source link
      (ffmpeg), NVIDIA redistributable license.
- [ ] Decide bundle-vs-download for ffmpeg (GPL obligations).
- [ ] Verify PyAV wheel's embedded FFmpeg build/license.
- [ ] Re-check NVIDIA EULA redistribution clause.
- [ ] Verify GigaAM weight license for shipped model names.
- [ ] Add a short in-app "About / third-party licenses" screen.
- [ ] Note in docs: yt-dlp usage subject to each site's ToS.
