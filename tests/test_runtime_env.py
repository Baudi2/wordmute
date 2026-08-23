"""Runtime environment manager: paths, status detection, pth patching,
activation — no network."""

import os
import sys

import pytest

from wordmute_app.core import runtime_env


@pytest.fixture
def fake_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path / "WordMute" / "runtime"


def _make_env(root, packages=(), ffmpeg=False, pip=True):
    site = root / "python" / "Lib" / "site-packages"
    site.mkdir(parents=True)
    (root / "python" / "python.exe").touch()
    if pip:
        (site / "pip").mkdir()
    for p in packages:
        (site / p).mkdir()
        # an install = the package dir AND pip's dist-info RECORD
        info = site / f"{p}-1.0.dist-info"
        info.mkdir()
        (info / "RECORD").write_text("", encoding="utf-8")
    if ffmpeg:
        (root / "ffmpeg").mkdir()
        (root / "ffmpeg" / "ffmpeg.exe").touch()


def test_status_empty(fake_runtime):
    s = runtime_env.status()
    assert not any(s.values())
    assert set(runtime_env.missing_required()) == \
        {"python", "ffmpeg", "whisper", "ytdlp"}


def test_status_complete(fake_runtime):
    _make_env(fake_runtime, packages=("faster_whisper", "yt_dlp",
                                      "nvidia"), ffmpeg=True)
    s = runtime_env.status()
    assert s["python"] and s["pip"] and s["ffmpeg"]
    assert s["faster_whisper"] and s["yt_dlp"] and s["cuda_dlls"]
    assert not s["gigaam"]
    assert runtime_env.missing_required() == []


def test_missing_partial(fake_runtime):
    _make_env(fake_runtime, packages=("faster_whisper",), ffmpeg=False)
    assert set(runtime_env.missing_required()) == {"ffmpeg", "ytdlp"}


def test_patch_pth(tmp_path):
    py = tmp_path / "python"
    py.mkdir()
    pth = py / "python312._pth"
    pth.write_text("python312.zip\n.\n\n#import site\n", encoding="utf-8")
    runtime_env._patch_pth(py)
    content = pth.read_text(encoding="utf-8")
    assert "\nimport site\n" in content
    assert "#import site" not in content
    assert "Lib\\site-packages" in content
    # idempotent
    runtime_env._patch_pth(py)
    assert content == pth.read_text(encoding="utf-8")


def test_activate_inserts_paths(fake_runtime, monkeypatch):
    _make_env(fake_runtime, packages=("yt_dlp",), ffmpeg=True)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setenv("PATH", "C:\\existing")
    monkeypatch.delenv("WORDMUTE_RUNTIME_SITE", raising=False)
    runtime_env.activate()
    assert str(runtime_env.site_packages()) in sys.path
    assert os.environ["WORDMUTE_RUNTIME_SITE"] == \
        str(runtime_env.site_packages())
    assert os.environ["PATH"].startswith(str(runtime_env.ffmpeg_dir()))


def test_activate_frozen_appends_stdlib_fallback(fake_runtime, monkeypatch):
    _make_env(fake_runtime, packages=("yt_dlp",), ffmpeg=True)
    zip_path = fake_runtime / "python" / "python312.zip"
    zip_path.touch()
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("WORDMUTE_RUNTIME_SITE", raising=False)
    runtime_env.activate()
    # stdlib fallback goes LAST so the frozen bundle always wins
    assert sys.path[-2] == str(zip_path)
    assert sys.path[-1] == str(runtime_env.python_dir())
    assert sys.path.index(str(runtime_env.site_packages())) == 1


def test_activate_not_frozen_skips_stdlib(fake_runtime, monkeypatch):
    _make_env(fake_runtime, packages=("yt_dlp",), ffmpeg=True)
    (fake_runtime / "python" / "python312.zip").touch()
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv("WORDMUTE_RUNTIME_SITE", raising=False)
    runtime_env.activate()
    assert str(fake_runtime / "python" / "python312.zip") not in sys.path


def test_activate_noop_without_env(fake_runtime, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv("WORDMUTE_RUNTIME_SITE", raising=False)
    before = list(sys.path)
    runtime_env.activate()
    assert sys.path == before
    assert "WORDMUTE_RUNTIME_SITE" not in os.environ


def test_write_report(fake_runtime, tmp_path):
    import json
    dest = tmp_path / "report.json"
    runtime_env.write_report(dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert "status" in data and "runtime_dir" in data


def test_components_are_sane():
    assert "faster-whisper" in \
        runtime_env.COMPONENTS["whisper_gpu"]["packages"]
    assert "nvidia-cublas-cu12" in \
        runtime_env.COMPONENTS["whisper_gpu"]["packages"]
    assert runtime_env.COMPONENTS["whisper_cpu"]["packages"] == \
        ["faster-whisper"]
    assert runtime_env.COMPONENTS["ytdlp"]["packages"] == ["yt-dlp"]
    # GigaAM ships via onnx-asr (CPU-fast, no torch/pyannote/HF token);
    # never the bare PyPI "gigaam" — PyPI is stale (0.1.0: no v3
    # models, no word timestamps)
    assert runtime_env.COMPONENTS["gigaam"]["packages"] == \
        ["onnx-asr[cpu,hub]"]


def _fake_ffmpeg_zip(dest):
    import zipfile
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("ffmpeg-x/bin/ffmpeg.exe", b"x")
        zf.writestr("ffmpeg-x/bin/ffprobe.exe", b"x")


def test_install_ffmpeg_falls_back_to_mirror(fake_runtime, monkeypatch):
    """Regression from the first tester: gyan.dev timed out and the
    whole setup died — now each host is tried twice, then the GitHub
    mirror takes over."""
    attempts = []

    def fake_download(url, dest, progress=None, cancelled=None,
                      timeout=60):
        attempts.append(url.split("/")[2])
        if "gyan.dev" in url:
            raise TimeoutError("The read operation timed out")
        _fake_ffmpeg_zip(dest)

    monkeypatch.setattr(runtime_env, "_download", fake_download)
    logs = []
    runtime_env.install_ffmpeg(log=logs.append)
    assert attempts == ["www.gyan.dev", "www.gyan.dev", "github.com"]
    assert (runtime_env.ffmpeg_dir() / "ffmpeg.exe").exists()
    assert (runtime_env.ffmpeg_dir() / "ffprobe.exe").exists()
    assert any("retry" in line for line in logs)


def test_install_ffmpeg_all_mirrors_down(fake_runtime, monkeypatch):
    def fake_download(url, dest, progress=None, cancelled=None,
                      timeout=60):
        raise TimeoutError("timed out")

    monkeypatch.setattr(runtime_env, "_download", fake_download)
    with pytest.raises(RuntimeError, match="every mirror"):
        runtime_env.install_ffmpeg()


def test_install_ffmpeg_cancel_not_retried(fake_runtime, monkeypatch):
    calls = []

    def fake_download(url, dest, progress=None, cancelled=None,
                      timeout=60):
        calls.append(url)
        raise runtime_env.SetupCancelled()

    monkeypatch.setattr(runtime_env, "_download", fake_download)
    with pytest.raises(runtime_env.SetupCancelled):
        runtime_env.install_ffmpeg()
    assert len(calls) == 1          # user cancel is not a network error


def test_default_gigaam_model_is_v3_rnnt(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.core import config
    assert config.load_settings()["gigaam_model"] == "v3_rnnt"


def test_setup_dialog_defaults(qapp, fake_runtime, monkeypatch):
    _make_env(fake_runtime, packages=("faster_whisper", "yt_dlp"),
              ffmpeg=False)
    from wordmute_app.core import gpu
    monkeypatch.setattr(gpu, "detect_gpus",
                        lambda: [gpu.GpuInfo("RTX", 8000)])
    from wordmute_app.ui.setup_dialog import SetupDialog

    d = SetupDialog(first_run=False)
    # installed components pre-unchecked and locked, missing checked
    assert not d.whisper_check.isChecked()
    assert not d.whisper_check.isEnabled()
    assert not d.ytdlp_check.isChecked()
    assert d.ffmpeg_check.isChecked()
    assert d.gpu_radio.isChecked()  # GPU detected
    # GigaAM defaults ON (verified backend, no account needed) and
    # brings its model with it; python already exists so it is skipped
    assert d.gigaam_check.isChecked()
    steps = d._build_steps()
    assert [name for name, _ in steps] == ["ffmpeg", "gigaam",
                                           "gigaam_model"]