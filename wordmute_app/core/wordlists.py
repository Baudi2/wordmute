"""Loading and combining word lists for a job.

The engine's load_wordlist parses one file; a job may use several lists
(Russian, English, or both). Merging happens here so the engine's
matching logic stays untouched."""

from pathlib import Path

from ..engine import wordmute as engine


def merge_wordlists(paths) -> tuple:
    """Load one or more word list files and merge them into a single
    (exact, stems, phrases, subs) tuple as expected by find_hits."""
    exact, stems, phrases, subs = set(), [], [], []
    for path in paths:
        e, st, ph, su = engine.load_wordlist(Path(path))
        exact |= e
        stems.extend(st)
        phrases.extend(ph)
        subs.extend(su)
    return exact, stems, phrases, subs
