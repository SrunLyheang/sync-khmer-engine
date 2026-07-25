"""Common-English detection for code-switching (roadmap Phase 3).

Khmer chat routinely mixes in English words ("ok", "message", "javascript"). The
engine should leave those as English rather than forcing them into Khmer. This
module loads a bundled list of common English words and answers ``is_english``.

The list is ``data/english_words.txt`` — the google-10000-english common-word list
(MIT-licensed), minus single letters and minus short spellings that are actually
Sing Khmer abbreviations (nh, sl, jg, …), so detection only fires on genuine
foreign words. A word that is *both* English and a real Khmer spelling (e.g.
``computer``) is still handled as Khmer first, with English offered as a hidden
last option (see ``lookup.Engine``).
"""

from __future__ import annotations

from pathlib import Path

# Default location of the bundled English wordlist, relative to the repo root.
DEFAULT_ENGLISH_PATH = Path(__file__).resolve().parents[2] / "data" / "english_words.txt"


def load_english(path: str | Path = DEFAULT_ENGLISH_PATH) -> frozenset[str]:
    """Load the bundled common-English wordlist into a lowercase set.

    Returns an empty set if the file is missing, so the engine still runs (English
    detection simply turns off) rather than failing to start.
    """
    path = Path(path)
    if not path.exists():
        return frozenset()
    with path.open(encoding="utf-8") as handle:
        return frozenset(
            word for word in (line.strip().lower() for line in handle) if word
        )


def is_english(word: str, words: frozenset[str]) -> bool:
    """True if ``word`` (case-insensitive) is in the common-English wordlist."""
    return word.strip().lower() in words
