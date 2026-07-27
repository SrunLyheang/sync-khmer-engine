"""Reverse index: Latin (Sing Khmer) spelling -> ranked Khmer candidates (step 1.6).

This is the actual runtime lookup table. It is built from two sources:

- **collected** — every romanization the team entered for a word maps to that word.
  This is ground truth and the backbone of the engine (it captures whole-word
  abbreviations like ``nh`` -> ខ្ញុំ that don't decompose into syllables).
- **generated** — plausible spelling *variants* produced by the romanizer (see
  ``sing_khmer_engine.romanizer``) for every word, so a reasonable spelling nobody
  has typed yet still matches. Because there is no single "correct" Sing Khmer
  spelling, this coverage layer is essential — but it is always scored *below*
  collected so real spellings win.

A single spelling can map to several Khmer words (homophones), so each key holds a
list of candidates ranked by score (word frequency, collected before generated).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .vocabulary import VocabEntry


@dataclass(frozen=True)
class Candidate:
    """One Khmer word suggested for a Latin spelling."""

    khmer: str
    score: float
    source: str          # "collected" or "generated"


def _norm(text: str) -> str:
    return text.strip().lower()


# Generated spellings are scored at frequency x this factor, so even a top-frequency
# generated variant (5 x 0.1 = 0.5) stays below the lowest collected score (1.0) — a real
# spelling always wins over a guessed one within the same key.
_GENERATED_DISCOUNT = 0.1


def build_index(
    vocab: list[VocabEntry],
    generate: Callable[[str], Iterable[str]] | None = None,
    *,
    max_generated_per_word: int = 6,
) -> dict[str, list[Candidate]]:
    """Build the reverse index mapping a normalized spelling to ranked candidates.

    Args:
        vocab: loaded vocabulary.
        generate: optional ``khmer -> plausible spellings`` function (the romanizer's
            ``variants``); when given, adds the generated coverage layer.
        max_generated_per_word: cap on generated spellings per word (avoids blow-up).
    """
    # key -> khmer -> (best_score, source)
    acc: dict[str, dict[str, tuple[float, str]]] = defaultdict(dict)

    def add(key: str, khmer: str, score: float, source: str) -> None:
        key = _norm(key)
        if not key:
            return
        cur = acc[key].get(khmer)
        if cur is None or score > cur[0]:
            acc[key][khmer] = (score, source)

    # collected (backbone)
    for e in vocab:
        for r in e.romanizations:
            add(r, e.khmer, float(e.frequency), "collected")

    # generated (coverage layer) — plausible variants, always below collected
    if generate is not None:
        for e in vocab:
            score = float(e.frequency) * _GENERATED_DISCOUNT
            for key in list(generate(e.khmer))[:max_generated_per_word]:
                add(key, e.khmer, score, "generated")

    # finalize: ranked candidate lists
    index: dict[str, list[Candidate]] = {}
    for key, by_khmer in acc.items():
        cands = [Candidate(k, round(s, 3), src) for k, (s, src) in by_khmer.items()]
        cands.sort(key=lambda c: (-c.score, c.source != "collected", c.khmer))
        index[key] = cands
    return index
