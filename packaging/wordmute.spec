# PyInstaller spec for the distributable WordMute build.
#
# Included: GUI, engine, yt-dlp, faster-whisper stack (ctranslate2,
# onnxruntime for VAD, PyAV) and the pip-installed NVIDIA cuBLAS/cuDNN
# DLLs so GPU whisper works on end-user machines with an NVIDIA driver.
# Deliberately EXCLUDED (v1): torch / GigaAM / pyannote — freezing that
# stack multiplies the size several-fold; GigaAM stays a developer-
# environment feature until the installer learns to set it up (v2).

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent

datas = [(str(ROOT / "wordmute_app" / "resources"), "wordmute_app/resources")]
binaries = []
hiddenimports = ["winsound"]

for pkg in ("faster_whisper", "ctranslate2", "av", "tokenizers",
            "onnxruntime", "huggingface_hub", "yt_dlp"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# pip-installed CUDA runtime DLLs (namespace package, no hooks)
import site
for sp in site.getsitepackages():
    for sub in ("cublas", "cudnn"):
        bin_dir = Path(sp) / "nvidia" / sub / "bin"
        if bin_dir.is_dir():
            for dll in bin_dir.glob("*.dll"):
                binaries.append((str(dll), f"nvidia/{sub}/bin"))

a = Analysis(
    [str(Path(SPECPATH) / "launch.py")],
    pathex=[str(ROOT)],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=[
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
