"""Word list tidying: lowercase, ё->е, strip, dedupe, sort.

Same semantics as the author's standalone sortwords.py — the app's word
list editor runs this automatically on save. Comment lines (#) are kept
and sorted along with the rest, matching the original behavior.
"""

from pathlib import Path


def tidy_lines(lines):
    """Return the tidied, sorted, deduplicated entries for the given lines."""
    entries = set()
    for raw in lines:
        line = raw.strip().lower().replace("ё", "е")  # ё -> е
        if line:
            entries.add(line)
    return sorted(entries)


def tidy_file(path) -> tuple[int, int]:
    """Tidy a word list file in place. Returns (kept, duplicates_removed)."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    result = tidy_lines(lines)
    path.write_text("\n".join(result) + "\n", encoding="utf-8")
    removed = len([l for l in lines if l.strip()]) - len(result)
    return len(result), removed
