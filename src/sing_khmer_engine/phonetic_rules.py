"""Phonetic rules: KCC -> plausible Latin (Sing Khmer) spellings + confidence (step 1.4).

A phonetic rule says "this Khmer syllable (KCC) can be typed these ways in Latin
letters, with these confidence weights." The rules are *derived from the collected
vocabulary* (each word's `romanizations`) rather than hand-authored, using **direct**
evidence: from single-KCC words, the whole romanization *is* that KCC's spelling —
unambiguous ground truth.

Weights are relative frequencies within a KCC (its most-attested spelling ~1.0),
so later steps can rank candidates. Spellings that are whole-word abbreviations
(e.g. ខ្ញុំ -> "nh") don't decompose into KCCs and are intentionally left to the
word-level reverse index (step 1.6), not forced into per-KCC rules here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .kcc import segment
from .vocabulary import VocabEntry


@dataclass(frozen=True)
class Rule:
    """One KCC -> Latin spelling mapping."""

    kcc: str
    spelling: str
    weight: float          # relative confidence within the KCC, 0 < w <= 1


def build_rules(vocab: list[VocabEntry]) -> dict[str, list[Rule]]:
    """Derive the phonetic-rules table from the vocabulary.

    Only single-KCC words contribute (their whole romanization is that KCC's
    spelling). Returns a mapping ``kcc -> [Rule, ...]`` sorted by weight (highest
    first).
    """
    # kcc -> spelling -> count
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in vocab:
        kccs = segment(e.khmer)
        if len(kccs) != 1:
            continue
        for rom in e.romanizations:
            rom = rom.strip()
            if rom:
                counts[kccs[0]][rom] += 1

    rules: dict[str, list[Rule]] = {}
    for kcc, spell_counts in counts.items():
        total = sum(spell_counts.values())
        rs = [
            Rule(kcc=kcc, spelling=sp, weight=round(c / total, 3))
            for sp, c in spell_counts.items()
        ]
        rs.sort(key=lambda r: (-r.weight, r.spelling))
        rules[kcc] = rs
    return rules


def coverage(vocab: list[VocabEntry], rules: dict[str, list[Rule]]) -> dict[str, int]:
    """How many unique KCCs got at least one rule, vs. total unique KCCs."""
    all_kccs = {k for e in vocab for k in segment(e.khmer)}
    covered = set(rules)
    return {
        "unique_kccs": len(all_kccs),
        "covered": len(all_kccs & covered),
        "uncovered": len(all_kccs - covered),
    }
