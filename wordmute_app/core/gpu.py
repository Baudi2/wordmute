"""GPU detection and honest model-fit advice.

Uses nvidia-smi (present with any NVIDIA driver install) instead of
importing torch — the whisper-only path doesn't ship torch at all.
VRAM figures are conservative estimates including runtime overhead."""

import subprocess
from dataclasses import dataclass

WHISPER_VRAM_MB = {"large-v3": 4700, "medium": 2600, "small": 1600,
                   "base": 1100}
WHISPER_FALLBACK_ORDER = ["medium", "small", "base"]
GIGAAM_VRAM_MB = 3000  # v3 models + pyannote VAD headroom

CPU_SPEED_NOTE = ("CPU mode: transcription runs roughly 2-4x slower than "
                  "on a GPU, but works everywhere.")


@dataclass
class GpuInfo:
    name: str
    vram_mb: int


def detect_gpus() -> list:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []
    gpus = []
    for line in r.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                gpus.append(GpuInfo(parts[0], int(float(parts[1]))))
            except ValueError:
                continue
    return gpus


def vram_required_mb(engine: str, model: str) -> int:
    if engine == "whisper":
        return WHISPER_VRAM_MB.get(model, WHISPER_VRAM_MB["large-v3"])
    return GIGAAM_VRAM_MB


def _whisper_fallback(vram_mb: int):
    for model in WHISPER_FALLBACK_ORDER:
        if WHISPER_VRAM_MB[model] <= vram_mb:
            return model
    return None


def plan_warnings(plan, device: str, gpus) -> list:
    """Human-readable warnings for the chosen plan/device on this
    machine. Advisory only — never blocks a run."""
    if device == "cpu":
        return [CPU_SPEED_NOTE]
    if not gpus:
        return ["No NVIDIA GPU detected, but the device is set to CUDA — "
                "processing will fail. Switch the device to CPU in "
                "Settings (slower, but works)."]
    gpu = max(gpus, key=lambda g: g.vram_mb)
    warnings = []
    for engine, model in dict.fromkeys(plan):
        need = vram_required_mb(engine, model)
        if need <= gpu.vram_mb:
            continue
        msg = (f"{engine} model '{model}' needs about {need / 1000:.1f} GB "
               f"of VRAM; {gpu.name} has {gpu.vram_mb / 1000:.1f} GB — it "
               "likely won't fit.")
        if engine == "whisper":
            fallback = _whisper_fallback(gpu.vram_mb)
            msg += (f" Try the '{fallback}' model or CPU mode."
                    if fallback else " Try CPU mode.")
        else:
            msg += " Try CPU mode."
        warnings.append(msg)
    return warnings
