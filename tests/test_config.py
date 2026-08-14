"""App data dir, first-run word list copies, settings persistence."""

from wordmute_app.core import config


def test_first_run_copies_templates(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    paths = config.ensure_user_wordlists()
    assert set(paths) == {"russian", "english"}
    for p in paths.values():
        assert p.exists()
        assert p.parent == tmp_path / "WordMute" / "wordlists"


def test_user_edits_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    paths = config.ensure_user_wordlists()
    paths["russian"].write_text("мое слово\n", encoding="utf-8")
    again = config.ensure_user_wordlists()
    assert again["russian"].read_text(encoding="utf-8") == "мое слово\n"


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    s = config.load_settings()
    # identical to the defaults except ui_language, which follows the
    # OS on a first run (installer and app must agree)
    assert s == {**config.DEFAULT_SETTINGS,
                 "ui_language": config.detect_ui_language()}
    s["model"] = "small"
    s["use_english"] = True
    config.save_settings(s)
    loaded = config.load_settings()
    assert loaded["model"] == "small"
    assert loaded["use_english"] is True


def test_corrupt_settings_fall_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config.data_dir()
    config._settings_path().write_text("{not json", encoding="utf-8")
    assert config.load_settings() == {
        **config.DEFAULT_SETTINGS,
        "ui_language": config.detect_ui_language()}
