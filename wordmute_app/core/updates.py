"""Update checks for the processing stack.

Three kinds of things can be outdated, each handled differently:
- pip packages (faster-whisper, gigaam, yt-dlp): PyPI knows the latest
  version; upgrading works only in a non-frozen install.
- whisper model weights: HF repos have revisions; the local cached sha
  (refs/main) is compared against the remote.
- GigaAM weights: no version API — they ship with the gigaam package.
"""

import json
import subprocess
import sys
import urllib.request
from importlib import metadata

from . import models as models_mod
from .proc import creationflags

PACKAGES = ("faster-whisper", "gigaam", "yt-dlp")


def installed_version(name: str):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def latest_pypi_version(name: str, timeout: int = 15):
    try:
        with urllib.request.urlopen(
                f"https://pypi.org/pypi/{name}/json", timeout=timeout) as r:
            return json.load(r)["info"]["version"]
    except Exception:
        return None


def is_newer(latest, installed) -> bool:
    if not latest or not installed:
        return False
    try:
        from packaging.version import Version
        return Version(latest) > Version(installed)
    except Exception:
        return latest != installed


def check_packages() -> list:
    """[{name, installed, latest, update}] for every stack package."""
    results = []
    for name in PACKAGES:
        installed = installed_version(name)
        latest = latest_pypi_version(name) if installed else None
        results.append({
            "name": name,
            "installed": installed,
            "latest": latest,
            "update": is_newer(latest, installed),
        })
    return results


def local_model_sha(repo: str):
    ref = models_mod.repo_cache_dir(repo) / "refs" / "main"
    try:
        return ref.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def remote_model_sha(repo: str):
    try:
        import huggingface_hub
        return huggingface_hub.HfApi().model_info(repo).sha
    except Exception:
        return None


def check_whisper_models() -> list:
    """Revision check for DOWNLOADED whisper models only."""
    results = []
    for st in models_mod.whisper_model_status():
        if not st["downloaded"]:
            continue
        local = local_model_sha(st["repo"])
        remote = remote_model_sha(st["repo"])
        results.append({
            "model": st["model"],
            "repo": st["repo"],
            "update": bool(local and remote and local != remote),
        })
    return results


def pip_upgrade(names) -> tuple:
    """Upgrade packages in-place. Returns (ok, output tail)."""
    if getattr(sys, "frozen", False):
        return False, ("packaged build: updates are delivered with app "
                       "releases, not via pip")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", *names]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=900, creationflags=creationflags())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return r.returncode == 0, (r.stdout + r.stderr)[-800:]
