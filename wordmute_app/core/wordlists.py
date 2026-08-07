"""Loading and combining word lists for a job.

The engine's load_wordlist parses one file; a job may use several lists
(Russian, English, or both). Merging happens here so the engine's
matching logic stays untouched."""

from pathlib import Path

from ..engine import wordmute as engine


def explain_matches(text: str, wordlist) -> tuple:
    """'Why was this muted?' tester. For each word of the input, list
    the word-list entries (in their original notation) that would catch
    it; also list phrase entries matched by the input as a sequence.
    Returns ([(word, [entries])...], [phrase_strings])."""
    exact, stems, phrases, subs = wordlist
    words = [w for w in (engine.norm(x) for x in text.split()) if w]
    per_word = []
    for w in words:
        entries = []
        if w in exact:
            entries.append(w)
        entries.extend(f"{s}*" for s in stems if w.startswith(s))
        entries.extend(f"*{s}*" for s in subs if s in w)
        per_word.append((w, entries))
    phrase_hits = []
    for ph in phrases:
        n = len(ph)
        if any(tuple(words[i:i + n]) == ph
               for i in range(len(words) - n + 1)):
            phrase_hits.append(" ".join(ph))
    return per_word, phrase_hits


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
