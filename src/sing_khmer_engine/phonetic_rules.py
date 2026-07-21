"""Phonetic rules: KCC -> plausible Latin (Sing Khmer) spellings + confidence (step 1.4).

A phonetic rule says "this Khmer syllable (KCC) can be typed these ways in Latin
letters, with these confidence weights." The rules are *derived from the collected
vocabulary* (each word's `romanizations`) rather than hand-authored, using two
evidence sources:

- **direct**  — from single-KCC words, the whole romanization *is* that KCC's
  spelling. Unambiguous ground truth (weight starts high).
- **aligned** — (EXPERIMENTAL, opt-in via ``include_aligned=True``) from two-KCC
  words where one KCC's spelling is already known: the known part is stripped off
  and the remainder is attributed to the other KCC. This is only a rough heuristic
  and can misattribute spellings when a romanization splits several ways, so it is
  OFF by default and must not be treated as ground truth.

Weights are relative frequencies within a KCC (its most-attested spelling ~1.0),
so later steps can rank candidates. This is a *first pass* — the roadmap's tuning
steps (1.8–1.10) refine it. Spellings that are whole-word abbreviations
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
    source: str            # "direct" or "aligned"


def _best_prefix(text: str, spellings: set[str]) -> str | None:
    """Longest spelling that `text` starts with, leaving a non-empty remainder."""
    best = None
    for s in spellings:
        if s and len(s) < len(text) and text.startswith(s):
            if best is None or len(s) > len(best):
                best = s
    return best


def _best_suffix(text: str, spellings: set[str]) -> str | None:
    """Longest spelling that `text` ends with, leaving a non-empty remainder."""
    best = None
    for s in spellings:
        if s and len(s) < len(text) and text.endswith(s):
            if best is None or len(s) > len(best):
                best = s
    return best


def build_rules(
    vocab: list[VocabEntry], *, include_aligned: bool = False
) -> dict[str, list[Rule]]:
    """Derive the phonetic-rules table from the vocabulary.

    Args:
        vocab: the loaded vocabulary entries.
        include_aligned: if True, also emit the EXPERIMENTAL two-KCC aligned rules
            (see module docstring). Off by default so only exact, trustworthy rules
            are produced.

    Returns a mapping ``kcc -> [Rule, ...]`` sorted by weight (highest first).
    """
    seg = {e.khmer: segment(e.khmer) for e in vocab}

    # (kcc, spelling) -> count ; and which source first attested it.
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    source: dict[tuple[str, str], str] = {}
    known: dict[str, set[str]] = defaultdict(set)

    def observe(kcc: str, spelling: str, src: str) -> bool:
        spelling = spelling.strip()
        if not spelling:
            return False
        counts[kcc][spelling] += 1
        known[kcc].add(spelling)
        source.setdefault((kcc, spelling), src)
        return True

    # 1) DIRECT evidence: single-KCC words.
    for e in vocab:
        kccs = seg[e.khmer]
        if len(kccs) == 1:
            for rom in e.romanizations:
                observe(kccs[0], rom, "direct")

    # 2) ALIGNED evidence (experimental, opt-in): two-KCC words, anchored on an
    #    already-known part. Iterate so newly-learned spellings anchor further words.
    for _ in range(5 if include_aligned else 0):
        learned = False
        for e in vocab:
            kccs = seg[e.khmer]
            if len(kccs) != 2:
                continue
            a, b = kccs
            for rom in e.romanizations:
                pre = _best_prefix(rom, known.get(a, set()))
                if pre is not None:
                    remainder = rom[len(pre):]
                    if remainder not in known.get(b, set()):
                        learned |= observe(b, remainder, "aligned")
                    continue
                suf = _best_suffix(rom, known.get(b, set()))
                if suf is not None:
                    remainder = rom[: len(rom) - len(suf)]
                    if remainder not in known.get(a, set()):
                        learned |= observe(a, remainder, "aligned")
        if not learned:
            break

    # 3) Build rules with relative weights per KCC.
    rules: dict[str, list[Rule]] = {}
    for kcc, spell_counts in counts.items():
        total = sum(spell_counts.values())
        rs = [
            Rule(kcc=kcc, spelling=sp, weight=round(c / total, 3),
                 source=source[(kcc, sp)])
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
