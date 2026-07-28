"""Quality hints for user submissions — sorts the queue, never empties it.

Spellings and Khmer words are scored 0 (clean) to 3 (almost certainly junk). **The score
decides where something appears, not whether it survives.** Anything scoring 2 or more is
stored with `status='flagged'` and shown in a "needs a look" tab; nothing is discarded.

That's a deliberate reversal. Score-3 items used to be dropped before they were written, and
`/api/feedback` still answered "Thank you!", so a real word could vanish with no trace
anywhere. Since these submissions are the entire point of the app, the cost of wrongly
deleting one is far higher than the cost of a human glancing at a bad row.

Criteria are tuned for Sing Khmer romanization specifically — a spelling that would be
nonsense in English (e.g. "srolanh") is perfectly valid here.
"""

from __future__ import annotations

import re

# ---- spelling (latin) checks -------------------------------------------------------

# Keyboard-mashing patterns: runs on a single row of QWERTY.
_KEYBOARD_RUNS = re.compile(
    r"qwer|wert|erty|rtyu|tyui|yuio|uiop|"
    r"asdf|sdfg|dfgh|fghj|ghjk|hjkl|"
    r"zxcv|xcvb|cvbn|vbnm|"
    r"poiu|oiuy|iuyt|u ytr|ytre|trew|"
    r"lkjh|kjhg|jhgf|hgf|gfds|fdsa|"
    r"mnbv|nbvc|bvcx|vcxz",
    re.IGNORECASE,
)

# Runs of 4+ identical characters.
_REPEAT_RUN = re.compile(r"(.)\1{3,}")

# Alternating character patterns (ababab, xyxyxy).
_ALTERNATE = re.compile(r"(.{2,3})\1{2,}")

# All-vowel or all-consonant with no structure.
_ALL_VOWEL = re.compile(r"^[aeiou]{4,}$")
_ALL_CONS = re.compile(r"^[bcdfghjklmnpqrstvwxyz]{8,}$")

# There is deliberately NO profanity wordlist here.
#
# Sing Khmer romanization is phonetic, so ordinary Khmer words land on English profanity by
# coincidence. Measured against data/vocabulary.csv, a wordlist rejected three spellings that
# are already verified in the dictionary:
#
#     porn -> ពាន់   (thousand)
#     sex  -> សុិច
#     die  -> ដៃ     (hand — currently stored as "dai")
#
# Blocking those quietly deletes some of the most common words in the language, and the person
# who submitted them never finds out. A human reading the queue spots an actual troll in a
# second; a regex cannot tell one from the word for "thousand".

# Domain-like or URL fragments that slipped past redaction.
_DOMAIN_LIKE = re.compile(r"\.(com|net|org|io|xyz|tk|ml|ga|cf)\b", re.IGNORECASE)

# ---- khmer (unicode) checks --------------------------------------------------------

# Pure gibberish Khmer: random consonants with no vowel or structure.
# A valid Khmer word/syllable has at least one base consonant + vowel or diacritic.
_KHMER_BASE = re.compile(r"[\u1780-\u17a2\u17a5-\u17b3]")      # consonants + independent vowels
_KHMER_MOD = re.compile(r"[\u17b6-\u17d3\u17dd]")               # dependent vowels, signs, coeng

# Repeated single Khmer character 4+ times.
_KHMER_REPEAT = re.compile(r"([\u1780-\u17ff])\1{3,}")


def score_spelling(text: str) -> tuple[int, str]:
    """Rate a romanized spelling. Returns (score, reason). Score 3 = definite trash."""
    t = text.strip().lower()
    if not t:
        return 3, "empty"

    # Length extremes
    if len(t) == 0:
        return 3, "empty"
    if len(t) > 30:
        return 3, "too_long"

    # Single ambiguous letter — keep it, could be real (e.g. "b" for បង)
    if len(t) == 1 and t.isalpha():
        return 1, "single_letter"

    # Keyboard mashing
    if _KEYBOARD_RUNS.search(t):
        return 3, "keyboard_mash"

    # Character repetition
    if _REPEAT_RUN.search(t):
        return 3, "repeated_chars"

    # Alternating
    if _ALTERNATE.search(t):
        return 2, "suspicious_pattern"

    # All vowels / all consonants
    if _ALL_VOWEL.match(t):
        return 3, "all_vowels"
    if _ALL_CONS.match(t):
        return 2, "all_consonants"

    # Domain-like
    if _DOMAIN_LIKE.search(t):
        return 3, "domain_like"

    # Vowel ratio sanity check — real Sing Khmer has a reasonable mix
    vowels = sum(1 for c in t if c in "aeiou")
    if len(t) > 4 and vowels == 0:
        return 2, "no_vowels"        # could be abbreviation, but suspicious
    if len(t) > 4 and vowels / len(t) > 0.8:
        return 2, "too_many_vowels"

    return 0, "clean"


def score_khmer(text: str) -> tuple[int, str]:
    """Rate a Khmer word. Returns (score, reason). Score 3 = definite trash."""
    t = text.strip()
    if not t:
        return 3, "empty"

    # Must contain at least one Khmer base character
    if not _KHMER_BASE.search(t):
        return 3, "no_khmer"

    # Repeated single character
    if _KHMER_REPEAT.search(t):
        return 3, "repeated_khmer"

    # Too many base characters without any modifiers (vowel/sign/coeng)
    # A string of bare consonants like "កងចឆជ" is probably random mashing
    bases = len(_KHMER_BASE.findall(t))
    mods = len(_KHMER_MOD.findall(t))
    if bases >= 5 and mods == 0:
        return 3, "bare_consonant_string"

    # Length sanity — real Khmer words rarely exceed 15 codepoints
    if len(t) > 25:
        return 2, "very_long_khmer"

    return 0, "clean"


def filter_submission(spelling: str | None, khmer: str | None) -> tuple[int, str]:
    """Combined filter for a (spelling, khmer) pair.

    Returns (score, reason) where:
      0 = clean
      1 = mild suspicion (keep, note)
      2 = suspicious (store flagged)
      3 = reject (don't store)
    """
    if not spelling or not khmer:
        return 3, "missing_field"

    s_score, s_reason = score_spelling(spelling)
    k_score, k_reason = score_khmer(khmer)

    # Either side being definite trash = reject
    if s_score == 3:
        return 3, f"bad_spelling: {s_reason}"
    if k_score == 3:
        return 3, f"bad_khmer: {k_reason}"

    # Combine: max of both scores
    combined = max(s_score, k_score)
    if combined >= 2:
        reasons = []
        if s_score >= 2:
            reasons.append(f"spelling({s_reason})")
        if k_score >= 2:
            reasons.append(f"khmer({k_reason})")
        return combined, ", ".join(reasons)

    if s_score == 1 and k_score == 1:
        return 1, "both_mild"

    if s_score == 1:
        return 1, f"spelling({s_reason})"
    if k_score == 1:
        return 1, f"khmer({k_reason})"

    return 0, "clean"
