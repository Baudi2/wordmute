"""Update checks: version comparison, package/model checks, upgrade
guard rails — no network (everything stubbed)."""

import pytest

from wordmute_app.core import updates


def test_is_newer_semver_and_dates():
    assert updates.is_newer("1.2.0", "1.1.0")
    assert not updates.is_newer("1.1.0", "1.1.0")
    assert not updates.is_newer("1.0.9", "1.1.0")
    # yt-dlp date-style versions
    assert updates.is_newer("2026.08.01", "2026.07.04")
    assert not updates.is_newer(None, "1.0")
    assert not updates.is_newer("1.0", None)


def test_check_packages_states(monkeypatch):
    # onnx-asr is the GigaAM package setup installs today (the legacy
    # torch "gigaam" made every onnx-only install read "not installed")
    versions = {"faster-whisper": "1.1.0", "onnx-asr": None,
                "yt-dlp": "2026.07.04"}
    latest = {"faster-whisper": "1.1.0", "yt-dlp": "2026.08.01"}
    monkeypatch.setattr(updates, "installed_version", versions.get)
    monkeypatch.setattr(updates, "latest_pypi_version",
                        lambda name, timeout=15: latest.get(name))

    result = {p["name"]: p for p in updates.check_packages()}
    assert result["faster-whisper"]["update"] is False
    assert result["onnx-asr"]["installed"] is None
    assert result["onnx-asr"]["latest"] is None  # never queried
    assert result["yt-dlp"]["update"] is True


def test_local_model_sha_reads_ref(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    repo = "Systran/faster-whisper-small"
    refs = tmp_path / "models--Systran--faster-whisper-small" / "refs"
    refs.mkdir(parents=True)
    (refs / "main").write_text("abc123\n", encoding="utf-8")
    assert updates.local_model_sha(repo) == "abc123"
    assert updates.local_model_sha("Systran/faster-whisper-base") is None


def test_check_whisper_models_only_downloaded(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    d = tmp_path / "models--Systran--faster-whisper-small"
    (d / "blobs").mkdir(parents=True)
    (d / "snapshots").mkdir()            # a complete hub cache layout
    (d / "blobs" / "w.bin").write_bytes(b"x")
    (d / "refs").mkdir()
    (d / "refs" / "main").write_text("oldsha", encoding="utf-8")
    monkeypatch.setattr(updates, "remote_model_sha",
                        lambda repo: "newsha")

    result = updates.check_whisper_models()
    assert len(result) == 1  # only the downloaded model is checked
    assert result[0]["model"] == "small"
    assert result[0]["update"] is True


def test_pip_upgrade_frozen_without_runtime_refuses(monkeypatch,
                                                    tmp_path):
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # no runtime env
    ok, message = updates.pip_upgrade(["yt-dlp"])
    assert ok is False
    assert "component setup" in message


def test_pip_upgrade_frozen_targets_runtime_python(monkeypatch,
                                                   tmp_path):
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from wordmute_app.core import runtime_env
    runtime_env.python_dir().mkdir(parents=True)
    runtime_env.python_exe().touch()
    assert updates._pip_python() == str(runtime_env.python_exe())


def test_models_tab_renders_update_results(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    from wordmute_app.ui.models_tab import ModelsTab

    tab = ModelsTab()
    tab._on_updates_result({
        "packages": [
            {"name": "faster-whisper", "installed": "1.1.0",
             "latest": "1.1.0", "update": False},
            {"name": "yt-dlp", "installed": "2026.07.04",
             "latest": "2026.08.01", "update": True},
        ],
        "models": [{"model": "large-v3", "repo": "r", "update": True}],
    })
    rows = tab._update_rows
    assert rows["faster-whisper"].state_label.text() == "up to date"
    assert rows["faster-whisper"].property("state") == "ok"
    assert rows["yt-dlp"].old_label.text() == "2026.07.04"
    assert rows["yt-dlp"].new_label.text() == "→ 2026.08.01"
    assert rows["yt-dlp"].button.text() == "Update"
    assert rows["yt-dlp"].property("state") == "new"
    assert "model:large-v3" in rows
    # one button morphs instead of a second one appearing
    assert tab.btn_check.property("mode") == "update"
    assert tab.btn_check.text() == "Update all (2)"
    assert tab._outdated_packages == ["yt-dlp"]
    assert tab._outdated_models == ["large-v3"]
    # the result is remembered, so the tab never opens empty again
    from wordmute_app.core import config
    assert config.load_settings()["updates_last"]["result"]["packages"]
