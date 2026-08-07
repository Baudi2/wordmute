"""Word list tidy logic mirrors sortwords.py."""

from wordmute_app.engine.wordlist_tidy import tidy_file, tidy_lines


def test_tidy_lines_dedup_sort_normalize():
    lines = ["Бог", "бог", "  ёлка  ", "", "елка", "ангел"]
    assert tidy_lines(lines) == ["ангел", "бог", "елка"]


def test_tidy_lines_keeps_comments():
    assert "# заметка" in tidy_lines(["# заметка", "слово"])


def test_tidy_file_in_place(tmp_path):
    p = tmp_path / "list.txt"
    p.write_text("Бог\nбог\nЁлка\n", encoding="utf-8")
    kept, removed = tidy_file(p)
    assert kept == 2 and removed == 1
    assert p.read_text(encoding="utf-8") == "бог\nелка\n"


def test_shipped_lists_are_already_tidy():
    # the bundled templates must be in canonical form (idempotent tidy)
    from pathlib import Path
    res = Path(__file__).resolve().parents[1] / "wordmute_app" / "resources"
    for name in ("words_russian.txt", "words_english.txt"):
        lines = (res / name).read_text(encoding="utf-8").splitlines()
        assert tidy_lines(lines) == [l for l in lines if l.strip()], name
