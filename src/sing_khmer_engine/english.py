"""Common-English detection for code-switching (roadmap Phase 3).

Khmer chat routinely mixes in English words ("ok", "message", "javascript"). The
engine should leave those as English rather than forcing them into Khmer. This
module loads a bundled list of common English words and answers ``is_english``.

The list is ``data/english_words.txt`` — the google-10000-english common-word list
(MIT-licensed), filtered as follows:

* single letters are dropped (they collide with everything and mean nothing);
* **short words (<= 3 letters) must be genuinely common** (inside the top ~1200 of the
  frequency-ordered source). That keeps real words like ``do``, ``no``, ``map``, ``tv``
  while dropping list noise and foreign fragments — ``dg``, ``der``, ``das``, ``av`` —
  which are far more likely to be Sing Khmer spellings (ដឹង, ដើរ, ដាស់, អាវ) than
  someone's English.

Longer words are kept as-is: a 4+ letter English word is rarely also a Sing Khmer spelling.

Note what this filter is *not* doing: it no longer removes words just because they collide
with the vocabulary. That protection lives in ``lookup._low_confidence_tokens``, which
refuses to pass a token through as English when it is a strong Khmer match. So a word that
is *both* (``computer``, ``map``, ``tv``) converts to Khmer as usual and simply gains an
English option the user can tap — which is the point.
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
