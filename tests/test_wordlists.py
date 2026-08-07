"""Merging several word lists into one engine tuple."""

from wordmute_app.core.wordlists import merge_wordlists


def test_merge_two_lists(tmp_path):
    ru = tmp_path / "ru.txt"
    ru.write_text("бог\nкорень*\n*внутри*\nбоже мой\n", encoding="utf-8")
    en = tmp_path / "en.txt"
    en.write_text("god\nwitch*\noh my god\n", encoding="utf-8")

    exact, stems, phrases, subs = merge_wordlists([ru, en])
    assert exact == {"бог", "god"}
    assert stems == ["корень", "witch"]
    assert subs == ["внутри"]
    assert set(phrases) == {("боже", "мой"), ("oh", "my", "god")}


def test_merge_single_list_matches_engine_load(tmp_path):
    from wordmute_app.engine import wordmute as engine
    p = tmp_path / "l.txt"
    p.write_text("слово\nстем*\n", encoding="utf-8")
    assert merge_wordlists([p]) == engine.load_wordlist(p)
