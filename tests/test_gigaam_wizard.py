"""Wizard offscreen: status flows with validation stubbed."""

import os


def make_wizard(qapp, tmp_path, monkeypatch, ffmpeg_found="C:\\ffmpeg\\bin"):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from wordmute_app.engine import wordmute as engine
    monkeypatch.setattr(engine, "discover_ffmpeg_shared_dir",
                        lambda: ffmpeg_found)
    from wordmute_app.ui.gigaam_wizard import GigaamWizard
    return GigaamWizard()


def test_ffmpeg_found_status(qapp, tmp_path, monkeypatch):
    w = make_wizard(qapp, tmp_path, monkeypatch)
    assert "✓" in w.ffmpeg_status.text()
    assert not w.recheck_button.isVisible()


def test_ffmpeg_missing_shows_hint(qapp, tmp_path, monkeypatch):
    w = make_wizard(qapp, tmp_path, monkeypatch, ffmpeg_found=None)
    assert "winget install Gyan.FFmpeg.Shared" in w.ffmpeg_status.text()


def test_success_saves_token_and_env(qapp, tmp_path, monkeypatch):
    from wordmute_app.core import config
    w = make_wizard(qapp, tmp_path, monkeypatch)
    monkeypatch.setenv("HF_TOKEN", "")
    w.token_edit.setText("hf_valid")
    w._on_ok("badic")
    assert config.load_hf_token() == "hf_valid"
    assert os.environ["HF_TOKEN"] == "hf_valid"
    assert "Signed in as badic" in w.token_status.text()


def test_failure_shows_message(qapp, tmp_path, monkeypatch):
    w = make_wizard(qapp, tmp_path, monkeypatch)
    w._on_failed("Hugging Face rejected the token")
    assert "rejected" in w.token_status.text()
    assert w.validate_button.isEnabled()


def test_empty_token_short_circuits(qapp, tmp_path, monkeypatch):
    w = make_wizard(qapp, tmp_path, monkeypatch)
    w.token_edit.setText("")
    w._validate()
    assert w._worker is None
    assert "Paste a token" in w.token_status.text()
