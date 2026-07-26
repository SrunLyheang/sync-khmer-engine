#!/usr/bin/env python3
"""Khmer -> Sing Khmer romanizer: predict how people would *type* a Khmer word.

This learns the romanization pattern from `data/vocabulary.csv` and applies it to new
words (the reverse direction of the engine). It's a research / vocabulary-growth tool —
it does NOT touch the shipped engine.

How it works (three layers, in priority order per syllable / KCC):

  1. Final-consonant reduction. A word-final bare consonant is spoken unreleased, so it's
     written short: ក->k, ង->ng, ស->s, ត->t … and final រ is usually dropped (silent).
  2. Learned whole-KCC spelling. If the vocabulary shows how a whole syllable is typed
     (directly, from single-syllable words, or by alignment — peeling a known syllable's
     spelling off a two-syllable word and attributing the rest to the other), use the
     best-attested spelling. Only spellings with real support are trusted (direct, or seen
     ≥2× via alignment), so one-off alignment noise is ignored.
  3. Compositional fallback. For a syllable the vocabulary has never shown, build it from a
     consonant table + a vowel table, where the vowel depends on the consonant's *series*
     (Khmer's two-series system: ា reads "a" after an a-series consonant, "ea" after an
     o-series one — e.g. ណា->na but មាស->meas).

Usage:
    PYTHONPATH=src python scripts/romanize.py ក្តី ខ្មៅ            # words as arguments
    PYTHONPATH=src python scripts/romanize.py --table words.txt    # markdown table from a file
    echo "ក្តី" | PYTHONPATH=src python scripts/romanize.py        # from stdin
    PYTHONPATH=src python scripts/romanize.py --accuracy           # round-trip score on the DB
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.kcc import segment  # noqa: E402
from sing_khmer_engine.vocabulary import load  # noqa: E402

_COENG = 0x17D2   # subscript marker
_BANTOC = 0x17CB  # ់  (shortens/638 marks a final consonant)

# Khmer's two consonant series. A dependent vowel is read differently after each — this is
# the single biggest reason the same vowel sign romanizes two ways.
_SERIES_2 = set("គឃងជឈញឌឍទធនពភមយរលវ")   # 2nd (o-) series; everything else is 1st (a-) series

# Base/subscript consonant -> Latin onset. Calibrated to how people actually type Sing
# Khmer (ច/ជ -> "j", not "ch"; aspirated ខ/ថ/ភ -> kh/th/ph).
_CONS = {
    "ក": "k", "ខ": "kh", "គ": "k", "ឃ": "kh", "ង": "ng", "ច": "j", "ឆ": "ch",
    "ជ": "j", "ឈ": "ch", "ញ": "nh", "ដ": "d", "ឋ": "th", "ឌ": "d", "ឍ": "th",
    "ណ": "n", "ត": "t", "ថ": "th", "ទ": "t", "ធ": "th", "ន": "n", "ប": "b",
    "ផ": "ph", "ព": "p", "ភ": "ph", "ម": "m", "យ": "y", "រ": "r", "ល": "l",
    "វ": "v", "ស": "s", "ហ": "h", "ឡ": "l", "អ": "",
}

# Dependent vowel -> (a-series reading, o-series reading). "" is the inherent vowel.
# Calibrated against user corrections (បិទ->bit, ស្លឹក->slerk, ដំរី->domrey, ចៀម->jeam).
_VOW = {
    "": ("o", "o"), "ា": ("a", "ea"), "ិ": ("i", "i"), "ី": ("ey", "ey"),
    "ឹ": ("er", "er"), "ឺ": ("eu", "eu"), "ុ": ("o", "u"), "ូ": ("o", "u"),
    "ួ": ("uo", "uo"), "ើ": ("er", "er"), "ឿ": ("oe", "oe"), "ៀ": ("ea", "ea"),
    "េ": ("e", "e"), "ែ": ("ae", "ea"), "ៃ": ("ai", "ey"), "ោ": ("ao", "ou"),
    "ៅ": ("ov", "ov"), "ុំ": ("om", "um"), "ំ": ("om", "um"), "ាំ": ("am", "oam"),
    "ះ": ("h", "h"),
}

# Independent vowels (they carry their own vowel, no base consonant).
_INDEP = {
    "ឥ": "e", "ឦ": "ey", "ឧ": "o", "ឩ": "u", "ឪ": "ov", "ឫ": "reu", "ឬ": "reu",
    "ឭ": "leu", "ឮ": "leu", "ឯ": "ae", "ឰ": "ai", "ឱ": "ao", "ឲ": "ao", "ឳ": "av",
}

# Word-final bare consonant -> its reduced (unreleased) reading. Final រ is usually silent.
_FINAL = {
    "ក": "k", "ខ": "k", "គ": "k", "ង": "ng", "ច": "ch", "ជ": "ch", "ញ": "nh",
    "ដ": "t", "ត": "t", "ថ": "t", "ទ": "t", "ធ": "t", "ន": "n", "ណ": "n",
    "ប": "p", "ព": "p", "ភ": "p", "ម": "m", "យ": "y", "រ": "", "ល": "l",
    "វ": "v", "ស": "s", "ហ": "h", "អ": "",
}

# Trust a learned spelling only with this much support: direct (1.0) or aligned seen >=2x
# (2 x 0.35 = 0.70). Filters one-off alignment noise.
_TRUST = 0.7
_ALIGN_WEIGHT = 0.35


def _is_cons(ch: str) -> bool:
    return 0x1780 <= ord(ch) <= 0x17A2


def _is_bare_final(kcc: str) -> bool:
    """A syllable that is a single consonant, optionally with ់ — i.e. a plain final."""
    return (len(kcc) == 1 and _is_cons(kcc[0])) or (
        len(kcc) == 2 and _is_cons(kcc[0]) and ord(kcc[1]) == _BANTOC
    )


def _compose(kcc: str) -> str:
    """Build a syllable's spelling from the consonant + vowel tables (layer 3)."""
    chars = list(kcc)
    if chars and chars[0] in _INDEP:               # independent-vowel syllable
        rest = "".join(chars[1:]).replace("់", "")
        tail = "h" if "ះ" in rest else ""
        return _INDEP[chars[0]] + tail
    onset: list[str] = []
    i = 0
    while i < len(chars):
        if _is_cons(chars[i]):
            onset.append(chars[i])
            i += 1
        elif ord(chars[i]) == _COENG and i + 1 < len(chars) and _is_cons(chars[i + 1]):
            onset.append(chars[i + 1])          # subscript consonant joins the onset
            i += 2
        else:
            break
    vowel = "".join(chars[i:]).replace("់", "").replace("៉", "").replace("៊", "")
    tail = ""
    if "ះ" in vowel:                               # final ះ reads as an "h"
        vowel = vowel.replace("ះ", "")
        tail = "h"
    series = 2 if (onset and onset[0] in _SERIES_2) else 1
    letters = "".join(_CONS.get(c, "") for c in onset)
    return letters + _VOW.get(vowel, ("", ""))[series - 1] + tail


def _best_affix(text: str, spellings: set[str], *, prefix: bool) -> str | None:
    best = None
    for s in spellings:
        if s and len(s) < len(text) and (text.startswith(s) if prefix else text.endswith(s)):
            if best is None or len(s) > len(best):
                best = s
    return best


def build_kcc_rules(vocab) -> dict[str, str]:
    """Learn a KCC -> best Latin spelling table (layers 1-2 evidence).

    Direct evidence comes from single-syllable words; alignment then peels known syllables
    off two-syllable words to attribute the remainder. Returns only well-supported spellings.
    """
    seg = {e.khmer: segment(e.khmer) for e in vocab}
    counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    known: dict[str, set[str]] = defaultdict(set)

    def observe(kcc: str, spelling: str, weight: float) -> None:
        spelling = spelling.strip().lower()
        if spelling:
            counts[kcc][spelling] += weight
            known[kcc].add(spelling)

    for e in vocab:                                    # direct: single-syllable words
        if len(seg[e.khmer]) == 1:
            for rom in e.romanizations:
                if " " not in rom:
                    observe(seg[e.khmer][0], rom, 1.0)

    for _ in range(8):                                 # alignment: iterate to convergence
        learned = False
        for e in vocab:
            kccs = seg[e.khmer]
            if len(kccs) != 2:
                continue
            a, b = kccs
            for rom in e.romanizations:
                if " " in rom:
                    continue
                pre = _best_affix(rom, known.get(a, set()), prefix=True)
                if pre is not None:
                    rem = rom[len(pre):]
                    if rem and rem not in known.get(b, set()):
                        observe(b, rem, _ALIGN_WEIGHT)
                        learned = True
                    continue
                suf = _best_affix(rom, known.get(b, set()), prefix=False)
                if suf is not None:
                    rem = rom[: len(rom) - len(suf)]
                    if rem and rem not in known.get(a, set()):
                        observe(a, rem, _ALIGN_WEIGHT)
                        learned = True
        if not learned:
            break

    rules: dict[str, str] = {}
    for kcc, spellings in counts.items():
        spelling, weight = max(spellings.items(), key=lambda kv: kv[1])
        if weight >= _TRUST:
            rules[kcc] = spelling
    return rules


def romanize(khmer: str, rules: dict[str, str]) -> str:
    """Predict the Sing Khmer spelling for one Khmer word."""
    kccs = segment(khmer)
    out: list[str] = []
    for i, kcc in enumerate(kccs):
        is_last = i == len(kccs) - 1
        if is_last and _is_bare_final(kcc):                       # 1. final reduction
            out.append(_FINAL.get(kcc[0], _CONS.get(kcc[0], "")))
        elif kcc in rules:                                        # 2. learned spelling
            out.append(rules[kcc])
        else:                                                     # 3. compositional
            out.append(_compose(kcc))
    return "".join(out)


def accuracy(vocab, rules: dict[str, str]) -> tuple[int, int]:
    """Round-trip: how many known words regenerate to a spelling the user actually typed."""
    hit = total = 0
    for e in vocab:
        if not e.romanizations:
            continue
        total += 1
        real = {r.replace(" ", "") for r in e.romanizations}
        if romanize(e.khmer, rules) in real:
            hit += 1
    return hit, total


def main() -> int:
    args = sys.argv[1:]
    vocab = load()
    rules = build_kcc_rules(vocab)

    if "--accuracy" in args:
        hit, total = accuracy(vocab, rules)
        print(f"round-trip exact match on the DB: {hit}/{total} = {100 * hit / total:.0f}%")
        return 0

    table = "--table" in args
    args = [a for a in args if a != "--table"]
    if args and Path(args[0]).exists():
        words = Path(args[0]).read_text(encoding="utf-8").split()
    elif args:
        words = args
    else:
        words = sys.stdin.read().split()

    db = {e.khmer for e in vocab}
    if table:
        print("| Khmer | predicted Sing Khmer | correct? (✅/✏️ fix) |")
        print("|-------|----------------------|----------------------|")
        for w in words:
            note = " _(already in DB)_" if w in db else ""
            print(f"| {w} | `{romanize(w, rules)}`{note} | |")
    else:
        for w in words:
            print(f"{w}\t{romanize(w, rules)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
