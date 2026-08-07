"""GPU detection parsing and plan-fit warnings."""

import subprocess

from wordmute_app.core import gpu


def fake_smi(monkeypatch, stdout, returncode=0):
    def fake_run(cmd, **kwargs):
        assert cmd[0] == "nvidia-smi"
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout,
                                           stderr="")
    monkeypatch.setattr(gpu.subprocess, "run", fake_run)


def test_detect_parses_output(monkeypatch):
    fake_smi(monkeypatch, "NVIDIA GeForce RTX 4060 Laptop GPU, 8188\n")
    gpus = gpu.detect_gpus()
    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA GeForce RTX 4060 Laptop GPU"
    assert gpus[0].vram_mb == 8188


def test_detect_no_nvidia_smi(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise OSError("not found")
    monkeypatch.setattr(gpu.subprocess, "run", fake_run)
    assert gpu.detect_gpus() == []


def test_detect_smi_error(monkeypatch):
    fake_smi(monkeypatch, "", returncode=1)
    assert gpu.detect_gpus() == []


PLAN = [("whisper", "large-v3"), ("gigaam", "v3_e2e_rnnt")]


def test_cpu_mode_gets_speed_note():
    w = gpu.plan_warnings(PLAN, "cpu", [])
    assert w == [gpu.CPU_SPEED_NOTE]


def test_cuda_without_gpu_warns():
    w = gpu.plan_warnings(PLAN, "cuda", [])
    assert len(w) == 1
    assert "will fail" in w[0]


def test_everything_fits_on_big_gpu():
    gpus = [gpu.GpuInfo("RTX 4060", 8188)]
    assert gpu.plan_warnings(PLAN, "cuda", gpus) == []


def test_large_model_on_small_gpu_suggests_fallback():
    gpus = [gpu.GpuInfo("GTX 1650", 4096)]
    w = gpu.plan_warnings([("whisper", "large-v3")], "cuda", gpus)
    assert len(w) == 1
    assert "large-v3" in w[0]
    assert "'medium'" in w[0]  # 2600 MB fits in 4096


def test_tiny_gpu_suggests_cpu_for_gigaam():
    gpus = [gpu.GpuInfo("MX150", 2048)]
    w = gpu.plan_warnings([("gigaam", "v3_e2e_rnnt")], "cuda", gpus)
    assert len(w) == 1
    assert "CPU mode" in w[0]


def test_duplicate_plan_entries_warn_once():
    gpus = [gpu.GpuInfo("GTX 1650", 4096)]
    w = gpu.plan_warnings([("whisper", "large-v3")] * 3, "cuda", gpus)
    assert len(w) == 1
