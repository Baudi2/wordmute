# PyInstaller spec for the SLIM WordMute build.
#
# The freeze contains only the app: GUI, engine code, themes/fonts,
# word lists, and huggingface_hub (model manager / GigaAM wizard).
# Engine packages (faster-whisper stack, yt-dlp, GigaAM) and ffmpeg
# are downloaded on first run into the app-managed runtime
# (%LOCALAPPDATA%\WordMute\runtime) — see core/runtime_env.py. The
# engine imports those packages lazily, so they must be EXCLUDED here
# or PyInstaller would happily freeze the dev machine's copies.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent

datas = [(str(ROOT / "wordmute_app" / "resources"), "wordmute_app/resources")]
binaries = []
hiddenimports = ["winsound"]

# Bundle the COMPLETE stdlib, not just what the app imports: runtime
# packages (yt-dlp especially) need stdlib modules the app never
# touches, and a partially bundled stdlib package (html without
# html.parser) shadows any runtime fallback path — the import system
# never consults sys.path for submodules of a bundled package.
_SKIP = {"antigravity", "this", "idlelib", "turtledemo", "turtle",
         "tkinter", "test", "lib2to3"}
for _mod in sorted(sys.stdlib_module_names):
    if _mod in _SKIP or _mod.startswith("_"):
        continue
    try:
        hiddenimports += collect_submodules(_mod)
    except Exception:
        hiddenimports.append(_mod)

for pkg in ("huggingface_hub",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(Path(SPECPATH) / "launch.py")],
    pathex=[str(ROOT)],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=[
        # runtime-environment packages — never freeze these
        "faster_whisper", "ctranslate2", "av", "tokenizers",
        "onnxruntime", "yt_dlp", "numpy",
        "torch", "torchaudio", "torchcodec", "gigaam", "pyannote",
        "lightning", "pytorch_lightning", "matplotlib", "tkinter",
        "IPython", "pytest",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtQuick",
        "PySide6.QtQml",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WordMute",
    console=False,
    icon=str(Path(SPECPATH) / "wordmute.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="WordMute")
