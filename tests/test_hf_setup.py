"""Hugging Face token validation and gated-model access checks, against
a fake huggingface_hub injected into sys.modules (no network)."""

import sys
import types

import pytest

from wordmute_app.core import hf_setup


class GatedRepoError(Exception):
    pass


def fake_hub(monkeypatch, whoami=None, auth_check=None):
    hub = types.ModuleType("huggingface_hub")

    class HfApi:
        def whoami(self, token=None):
            if whoami is None:
                raise RuntimeError("401 Unauthorized")
            return whoami

    hub.HfApi = HfApi
    if auth_check is not None:
        hub.auth_check = auth_check
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    return hub


def test_empty_token_rejected_before_network():
    with pytest.raises(hf_setup.SetupError, match="[Pp]aste"):
        hf_setup.validate_token("   ")


def test_valid_token_returns_username(monkeypatch):
    fake_hub(monkeypatch, whoami={"name": "badic"})
    assert hf_setup.validate_token("hf_x") == "badic"


def test_rejected_token_gives_friendly_error(monkeypatch):
    fake_hub(monkeypatch, whoami=None)
    with pytest.raises(hf_setup.SetupError, match="rejected"):
        hf_setup.validate_token("hf_bad")


def test_gated_access_ok(monkeypatch):
    fake_hub(monkeypatch, whoami={"name": "x"},
             auth_check=lambda repo, token=None: None)
    hf_setup.check_pyannote_access("hf_x")  # no exception


def test_gated_access_not_accepted(monkeypatch):
    def raise_gated(repo, token=None):
        raise GatedRepoError("gated")
    fake_hub(monkeypatch, whoami={"name": "x"}, auth_check=raise_gated)
    with pytest.raises(hf_setup.SetupError, match="access form"):
        hf_setup.check_pyannote_access("hf_x")


def test_other_errors_wrapped(monkeypatch):
    def boom(repo, token=None):
        raise ConnectionError("offline")
    fake_hub(monkeypatch, whoami={"name": "x"}, auth_check=boom)
    with pytest.raises(hf_setup.SetupError, match="offline"):
        hf_setup.check_pyannote_access("hf_x")


def test_token_storage_roundtrip(tmp_path, monkeypatch):
    from wordmute_app.core import config
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.load_hf_token() == ""
    config.save_hf_token("  hf_secret  ")
    assert config.load_hf_token() == "hf_secret"
    # token lives outside settings.json
    assert "hf_secret" not in (tmp_path / "WordMute" / "settings.json").name
    assert config.hf_token_path().read_text(encoding="utf-8").strip() \
        == "hf_secret"
