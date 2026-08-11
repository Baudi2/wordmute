"""App-managed runtime environment (slim-installer architecture).

The installer ships only the app; the heavy pieces are downloaded on
first run into %LOCALAPPDATA%\\WordMute\\runtime:
  runtime/python/   embeddable CPython + pip + engine packages
  runtime/ffmpeg/   ffmpeg.exe + ffprobe.exe (gyan.dev essentials)

The frozen app imports engine packages from the runtime's
site-packages (the engine imports them lazily, so sys.path insertion
at startup is enough) and prepends runtime/ffmpeg to PATH. A dev
checkout with packages installed normally never needs any of this.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from .proc import creationflags

PYTHON_VERSION = "3.12.10"
PYTHON_EMBED_URL = (f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
                    f"python-{PYTHON_VERSION}-embed-amd64.zip")
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
FFMPEG_URL = ("https://www.gyan.dev/ffmpeg/builds/"
              "ffmpeg-release-essentials.zip")

# component -> pip packages. Sizes are rough download estimates shown
# in the setup UI; keep them honest.
COMPONENTS = {
    "whisper_gpu": {
        "packages": ["faster-whisper", "nvidia-cublas-cu12",
                     "nvidia-cudnn-cu12"],
        "download_gb": 1.6,
    },
    "whisper_cpu": {
        "packages": ["faster-whisper"],
        "download_gb": 0.3,
    },
    "ytdlp": {
        "packages": ["yt-dlp"],
        "download_gb": 0.01,
    },
    "gigaam": {
        # onnx-asr runtime: GigaAM v3 on plain CPU (~43-59x realtime),
        # silero VAD, no torch/pyannote and no Hugging Face account;
        # the ~850 MB model downloads on first use like whisper's
        "packages": ["onnx-asr[cpu,hub]"],
        "download_gb": 0.06,
    },
}


class SetupCancelled(Exception):
    pass


def runtime_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(root) / "WordMute" / "runtime"


def python_dir() -> Path:
    return runtime_dir() / "python"


def python_exe() -> Path:
    return python_dir() / "python.exe"


def site_packages() -> Path:
    return python_dir() / "Lib" / "site-packages"


def ffmpeg_dir() -> Path:
    return runtime_dir() / "ffmpeg"


def package_installed(module_name: str) -> bool:
    return (site_packages() / module_name).is_dir()


def status() -> dict:
    return {
        "python": python_exe().exists(),
        "pip": (site_packages() / "pip").is_dir(),
        "ffmpeg": (ffmpeg_dir() / "ffmpeg.exe").exists(),
        "faster_whisper": package_installed("faster_whisper"),
        "cuda_dlls": (site_packages() / "nvidia").is_dir(),
        "yt_dlp": package_installed("yt_dlp"),
        # either backend counts: onnx-asr (current) or torch (legacy)
        "gigaam": (package_installed("onnx_asr")
                   or package_installed("gigaam")),
    }


def missing_required() -> list:
    """What must exist before the frozen app can work at all."""
    s = status()
    missing = []
    if not s["python"] or not s["pip"]:
        missing.append("python")
    if not s["ffmpeg"]:
        missing.append("ffmpeg")
    if not s["faster_whisper"]:
        missing.append("whisper")
    if not s["yt_dlp"]:
        missing.append("ytdlp")
    return missing


def activate() -> None:
    """Make the runtime visible to this process. Safe to call always;
    no-ops for anything not installed."""
    site = site_packages()
    if site.is_dir() and str(site) not in sys.path:
        # after the frozen bundle, before stdlib fallbacks
        sys.path.insert(1, str(site))
        # the engine's CUDA-DLL discovery checks this seam
        os.environ["WORDMUTE_RUNTIME_SITE"] = str(site)
    if getattr(sys, "frozen", False):
        # PyInstaller bundles only the stdlib modules the app itself
        # imports; runtime packages need more (yt-dlp pulls in wide
        # swaths of the stdlib). The runtime ships the full stdlib of
        # the SAME interpreter version — append it as a last-resort
        # fallback so bundled modules always win.
        py = python_dir()
        short = "".join(PYTHON_VERSION.split(".")[:2])
        for extra in (py / f"python{short}.zip", py):
            if extra.exists() and str(extra) not in sys.path:
                sys.path.append(str(extra))
        if py.is_dir():
            try:
                os.add_dll_directory(str(py))  # for stdlib .pyd deps
            except OSError:
                pass
    ff = ffmpeg_dir()
    if (ff / "ffmpeg.exe").exists():
        os.environ["PATH"] = (str(ff) + os.pathsep
                              + os.environ.get("PATH", ""))


# ---------------------------------------------------------------- steps
def _download(url: str, dest: Path, progress=None, cancelled=None,
              timeout: int = 60) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url, headers={"User-Agent": "WordMute-setup"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                if cancelled and cancelled():
                    raise SetupCancelled()
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)


def _patch_pth(py_dir: Path) -> None:
    """The embeddable build ships with site-packages disabled; enable
    it so pip-installed packages import."""
    for pth in py_dir.glob("python*._pth"):
        lines = pth.read_text(encoding="utf-8").splitlines()
        patched = []
        for line in lines:
            if line.strip() == "#import site":
                line = "import site"
            patched.append(line)
        if "Lib\\site-packages" not in patched:
            patched.append("Lib\\site-packages")
        pth.write_text("\n".join(patched) + "\n", encoding="utf-8")


def install_python(log=None, progress=None, cancelled=None) -> None:
    """Embeddable CPython + pip into runtime/python."""
    work = runtime_dir() / "tmp"
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / "python-embed.zip"
    if log:
        log(f"Downloading Python {PYTHON_VERSION}…")
    _download(PYTHON_EMBED_URL, zip_path, progress, cancelled)
    if python_dir().exists():
        shutil.rmtree(python_dir(), ignore_errors=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(python_dir())
    _patch_pth(python_dir())
    get_pip = work / "get-pip.py"
    if log:
        log("Installing pip…")
    _download(GET_PIP_URL, get_pip, progress, cancelled)
    _run_streaming([str(python_exe()), str(get_pip),
                    "--no-warn-script-location"], log, cancelled)
    shutil.rmtree(work, ignore_errors=True)


def install_ffmpeg(log=None, progress=None, cancelled=None) -> None:
    work = runtime_dir() / "tmp"
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / "ffmpeg.zip"
    if log:
        log("Downloading ffmpeg…")
    _download(FFMPEG_URL, zip_path, progress, cancelled)
    extract = work / "ffmpeg-extract"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract)
    ffmpeg_dir().mkdir(parents=True, exist_ok=True)
    found = 0
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        for candidate in extract.rglob(name):
            shutil.copy2(candidate, ffmpeg_dir() / name)
            found += 1
            break
    shutil.rmtree(work, ignore_errors=True)
    if found < 2:
        raise RuntimeError("ffmpeg archive did not contain the expected "
                           "executables")


def install_packages(packages, log=None, cancelled=None) -> None:
    _run_streaming(
        [str(python_exe()), "-m", "pip", "install", "--upgrade",
         "--no-warn-script-location", *packages], log, cancelled)


def _run_streaming(cmd, log=None, cancelled=None) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace",
                            creationflags=creationflags())
    for line in proc.stdout:
        if cancelled and cancelled():
            proc.kill()
            raise SetupCancelled()
        line = line.rstrip()
        if line and log:
            log(line)
    proc.wait()
    if proc.returncode:
        raise RuntimeError(f"command failed (code {proc.returncode}): "
                           f"{' '.join(cmd[:3])}…")


def disk_usage() -> int:
    """Total bytes of the managed runtime (components). Walks the
    tree — call from a worker thread, not the GUI thread."""
    total = 0
    root = runtime_dir()
    if root.is_dir():
        for path in root.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
    return total


def write_report(dest) -> None:
    """Diagnostics for support: WORDMUTE_RUNTIME_REPORT=<file>.
    Import probes prove the frozen app can actually use the runtime's
    packages, not just that their folders exist."""
    imports = {}
    for module in ("faster_whisper", "yt_dlp", "onnx_asr"):
        try:
            __import__(module)
            imports[module] = True
        except Exception as exc:
            imports[module] = f"{type(exc).__name__}: {exc}"[:200]
    Path(dest).write_text(
        json.dumps({"runtime_dir": str(runtime_dir()),
                    "status": status(),
                    "imports": imports,
                    "frozen": bool(getattr(sys, "frozen", False))},
                   indent=1),
        encoding="utf-8")
