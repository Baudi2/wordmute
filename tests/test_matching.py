"""Matching-engine behavior: norm, load_wordlist, find_hits."""

import pytest

from wordmute_app.engine import wordmute as wm


def W(items):
    """Build a transcript word list from (word, start, end) tuples."""
    return [{"w": w, "s": s, "e": e} for w, s, e in items]


# ---------------------------------------------------------------- norm
def test_norm_lowercase_and_yo():
    assert wm.norm("Ёжик") == "ежик"
    assert wm.norm("ВСЁ") == "все"


def test_norm_strips_punctuation_keeps_hyphen():
    assert wm.norm("слово,") == "слово"
    assert wm.norm("«кто-то»") == "кто-то"
    assert wm.norm("what's") == "whats"


# ---------------------------------------------------------------- load_wordlist
def test_load_wordlist_entry_types(tmp_path):
    p = tmp_path / "list.txt"
    p.write_text(
        "# a comment\n"
        "\n"
        "слово\n"
        "корень*\n"
        "*внутри*\n"
        "два слова\n"
        "Ёлка\n",
        encoding="utf-8",
    )
    exact, stems, phrases, subs = wm.load_wordlist(p)
    assert exact == {"слово", "елка"}          # comment/blank skipped, ё->е
    assert stems == ["корень"]
    assert subs == ["внутри"]
    assert phrases == [("два", "слова")]


def test_load_wordlist_single_star_is_not_substring(tmp_path):
    # "*x" (leading star only) must not be parsed as substring; per format
    # only *root* with both stars and content is a substring entry
    p = tmp_path / "list.txt"
    p.write_text("*ab*\n**\n", encoding="utf-8")
    exact, stems, phrases, subs = wm.load_wordlist(p)
    assert subs == ["ab"]
    assert "" not in subs


# ---------------------------------------------------------------- find_hits
LIST_KW = dict(pad_ms=100)


def hits(words, exact=(), stems=(), phrases=(), subs=(), pad_ms=100):
    return wm.find_hits(words, set(exact), list(stems), list(phrases),
                        list(subs), pad_ms)


def test_exact_hit_with_padding():
    words = W([("привет", 1.0, 1.5), ("бог", 3.0, 3.4), ("мир", 5.0, 5.5)])
    got = hits(words, exact=["бог"])
    assert len(got) == 1
    s, e, t = got[0]
    assert t == "бог"
    assert s == pytest.approx(2.9)   # full 100ms pad, far from neighbors
    assert e == pytest.approx(3.5)


def test_padding_never_bleeds_into_neighbors():
    words = W([("привет", 1.0, 2.98), ("бог", 3.0, 3.4), ("мир", 3.45, 5.5)])
    got = hits(words, exact=["бог"])
    s, e, _ = got[0]
    assert s == pytest.approx(2.98)  # clamped to previous word's end
    assert e == pytest.approx(3.45)  # clamped to next word's start


def test_stem_and_substring():
    words = W([("колдовать", 0.0, 0.5), ("монстрация", 1.0, 1.5),
               ("демонстрация", 2.0, 2.5)])
    got = hits(words, stems=["колд"], subs=["монстр"])
    # stem matches prefix; substring matches anywhere including "демонстрация"
    assert [t for _, _, t in got] == ["колдовать", "монстрация", "демонстрация"]


def test_phrase_consecutive_only():
    words = W([("боже", 0.0, 0.4), ("мой", 0.5, 0.9),
               ("боже", 2.0, 2.4), ("не", 2.5, 2.6), ("мой", 2.7, 3.0)])
    got = hits(words, phrases=[("боже", "мой")])
    assert len(got) == 1
    assert got[0][2] == "боже мой"


def test_overlapping_hits_merge():
    words = W([("бог", 1.0, 1.5), ("черт", 1.55, 2.0)])
    got = hits(words, exact=["бог", "черт"])
    assert len(got) == 1
    s, e, t = got[0]
    assert t == "бог | черт"
    assert s <= 1.0 and e >= 2.0


def test_empty_normed_words_skipped():
    words = W([("...", 0.0, 0.2), ("бог", 1.0, 1.5)])
    got = hits(words, exact=["бог"])
    assert len(got) == 1


def test_no_hits_returns_empty():
    words = W([("обычный", 0.0, 0.5), ("текст", 1.0, 1.5)])
    assert hits(words, exact=["бог"]) == []


def test_matching_is_case_and_yo_insensitive():
    words = W([("Чёрт,", 1.0, 1.5)])
    got = hits(words, exact=["черт"])
    assert len(got) == 1
