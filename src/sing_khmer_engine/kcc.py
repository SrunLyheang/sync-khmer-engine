"""Khmer Character Cluster (KCC) segmentation.

A KCC is the inseparable, syllable-level orthographic unit of Khmer: a base
character (consonant or independent vowel) together with any subscript
consonants (introduced by the *coeng* mark) and any dependent vowel signs or
diacritics attached to it. A vowel sign can never stand alone — it always
belongs to a base — so the mapping engine works at the KCC level rather than on
individual code points (roadmap step 1.3).

The single public function is :func:`segment`.

Example:
    >>> segment("ចឹង")
    ['ចឹ', 'ង']
    >>> segment("ស្អាត")
    ['ស្អា', 'ត']

The algorithm is a small Unicode rule (no external dependency): a new cluster
starts at each base character, *unless* that base immediately follows a coeng
(making it a subscript of the current cluster). Dependent vowels, signs, and the
coeng itself always attach to the current cluster. Non-Khmer characters (spaces,
Latin letters, digits, punctuation) each become their own token and break the
current cluster.
"""

from __future__ import annotations

# Khmer Unicode ranges (see the Unicode "Khmer" block, U+1780–U+17FF).
_CONSONANT_START, _CONSONANT_END = 0x1780, 0x17A2  # base consonants ក–អ
_INDEP_VOWEL_START, _INDEP_VOWEL_END = 0x17A5, 0x17B3  # independent vowels
_DEP_VOWEL_START, _DEP_VOWEL_END = 0x17B6, 0x17C5  # dependent vowel signs
_SIGN_START, _SIGN_END = 0x17C6, 0x17D1  # signs (nikahit, toandakhiat, etc.)
_COENG = 0x17D2  # the subscript ("coeng") marker
_SItself = 0x17D3  # bathamasat
_ATTHACAN = 0x17DD  # atthacan sign


def _is_base(cp: int) -> bool:
    return (
        _CONSONANT_START <= cp <= _CONSONANT_END
        or _INDEP_VOWEL_START <= cp <= _INDEP_VOWEL_END
    )


def _is_combining(cp: int) -> bool:
    """Marks that attach to the current cluster (vowels, signs), excluding coeng."""
    return (
        _DEP_VOWEL_START <= cp <= _DEP_VOWEL_END
        or _SIGN_START <= cp <= _SIGN_END
        or cp == _SItself
        or cp == _ATTHACAN
    )


def segment(text: str) -> list[str]:
    """Split ``text`` into Khmer Character Clusters.

    Non-Khmer characters (spaces, Latin, digits, punctuation) are each returned
    as their own single-character token, so the result concatenates back to the
    original string.

    Args:
        text: A Khmer (or mixed) string.

    Returns:
        The clusters in order. ``"".join(segment(text)) == text`` always holds.
    """
    clusters: list[str] = []
    current = ""
    subscript_pending = False  # True right after a coeng: next base is a subscript

    for ch in text:
        cp = ord(ch)
        if cp == _COENG:
            # Coeng attaches to the current cluster and pulls the next base in.
            if not current:
                # Defensive: a stray coeng with no base — treat as its own token.
                clusters.append(ch)
                continue
            current += ch
            subscript_pending = True
        elif _is_base(cp):
            if subscript_pending and current:
                current += ch  # subscript consonant of the current cluster
                subscript_pending = False
            else:
                if current:
                    clusters.append(current)
                current = ch
        elif _is_combining(cp):
            if current:
                current += ch
            else:
                clusters.append(ch)  # combining mark with no base — keep as-is
            subscript_pending = False
        else:
            # Non-Khmer: flush current cluster, emit this char on its own.
            if current:
                clusters.append(current)
                current = ""
            clusters.append(ch)
            subscript_pending = False

    if current:
        clusters.append(current)
    return clusters
