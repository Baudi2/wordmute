"""Model manager backend: what's downloaded where, sizes, delete,
download. Whisper models live in the Hugging Face hub cache under
Systran's faster-whisper repos; GigaAM manages its own cache and is
reported as a whole."""

import os
import shutil
from pathlib import Path

WHISPER_REPOS = {
    "large-v3": "Systran/faster-whisper-large-v3",
    # faster-whisper's own name map resolves "large-v3-turbo" to this
    # repo — the Models tab must track the same cache entry
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "medium": "Systran/faster-whisper-medium",
    "small": "Systran/faster-whisper-small",
    "base": "Systran/faster-whisper-base",
}


# catalogue sizes, so the Models tab can state what a download costs
# BEFORE it happens (design: the Size column never sits empty)
MODEL_CATALOG_BYTES = {
    "large-v3": 3_090_000_000,
    "large-v3-turbo": 1_620_000_000,
    "medium": 1_530_000_000,
    "small": 484_000_000,
    "base": 145_000_000,
    "gigaam": 851_000_000,
}


def snapshot_download_command(model: str) -> list:
    """A subprocess command that downloads one whisper model into the
    hub cache — run OUT of process so the Models tab can cancel it
    (huggingface_hub's snapshot_download cannot be interrupted in a
    thread). The frozen app has no python of its own: the managed
    runtime's interpreter carries huggingface_hub via faster-whisper."""
    import sys
    from . import runtime_env
    python = (str(runtime_env.python_exe())
              if runtime_env.python_exe().exists() else sys.executable)
    return [python, "-c",
            "import sys, huggingface_hub as h; "
            "h.snapshot_download(sys.argv[1])", WHISPER_REPOS[model]]


def hf_hub_cache() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def repo_cache_dir(repo: str) -> Path:
    return hf_hub_cache() / ("models--" + repo.replace("/", "--"))


def dir_size(path) -> int:
    total = 0
    for p in Path(path).rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def fmt_size(n: int) -> str:
    gb = n / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} GB"
    return f"{n / (1024 ** 2):.0f} MB"


def whisper_model_status() -> list:
    """[{model, repo, downloaded, size_bytes}] for every known model."""
    out = []
    for model, repo in WHISPER_REPOS.items():
        d = repo_cache_dir(repo)
        downloaded = d.is_dir()
        out.append({"model": model, "repo": repo, "downloaded": downloaded,
                    "size_bytes": dir_size(d) if downloaded else 0})
    return out


def delete_whisper_model(model: str) -> None:
    shutil.rmtree(repo_cache_dir(WHISPER_REPOS[model]), ignore_errors=True)


def download_whisper_model(model: str) -> None:
    """Blocking download (run in a worker thread from the UI)."""
    import huggingface_hub
    huggingface_hub.snapshot_download(WHISPER_REPOS[model])


def gigaam_cache_dirs() -> list:
    """[(path, size_bytes)] for existing GigaAM caches."""
    candidates = [Path.home() / ".cache" / "gigaam"]
    hub = hf_hub_cache()
    if hub.is_dir():
        candidates.extend(sorted(hub.glob("models--*[Gg]iga[Aa][Mm]*")))
    return [(p, dir_size(p)) for p in candidates if p.is_dir()]


def delete_gigaam_caches() -> None:
    for p, _ in gigaam_cache_dirs():
        shutil.rmtree(p, ignore_errors=True)
