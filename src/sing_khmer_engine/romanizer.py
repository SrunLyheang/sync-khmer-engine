"""Khmer -> Sing Khmer romanizer: predict how people *type* a Khmer word.

Learned from ``data/vocabulary.csv``, this is the reverse of the lookup engine. Two
public entry points on :class:`Romanizer`:

- ``romanize(khmer)``  — the single best-guess spelling (for tables / the CLI).
- ``variants(khmer)``  — a small SET of plausible spellings, because there is no one
  "correct" Sing Khmer spelling. The engine feeds these into its *generated* layer so a
  reasonable spelling nobody has typed yet still matches (coverage, not correctness).

How a syllable (KCC) is spelled, in priority order:

  1. Final/coda reduction. A bare consonant that isn't word-initial closes a syllable and
     takes no vowel (medial យ in គុយទាវ is just "y"); word-final រ is usually silent, and
     final ស/ះ waver between "s" and "h".
  2. Learned whole-KCC spelling, from the vocabulary (single-syllable direct evidence, plus
     alignment that peels a known syllable off a two-syllable word). Only well-supported
     spellings are kept, so one-off noise is ignored.
  3. Compositional fallback: consonant table + a *series*-aware vowel table (Khmer's two
     series make ា read "a" vs "ea": ណា->na but មាស->meas).
"""

from __future__ import annotations

from collections import defaultdict

from .kcc import segment
from .vocabulary import VocabEntry

_COENG = 0x17D2   # subscript ("coeng") marker
_BANTOC = 0x17CB  # ់  marks a short/final consonant

# Khmer's two consonant series — the single biggest reason a vowel romanizes two ways.
_SERIES_2 = set("គឃងជឈញឌឍទធនពភមយរលវ")   # 2nd (o-) series; the rest are 1st (a-) series

# Base/subscript consonant -> Latin onset (ច/ជ -> "j", aspirated ខ/ថ/ភ -> kh/th/ph).
_CONS = {
    "ក": "k", "ខ": "kh", "គ": "k", "ឃ": "kh", "ង": "ng", "ច": "j", "ឆ": "ch",
    "ជ": "j", "ឈ": "ch", "ញ": "nh", "ដ": "d", "ឋ": "th", "ឌ": "d", "ឍ": "th",
    "ណ": "n", "ត": "t", "ថ": "th", "ទ": "t", "ធ": "th", "ន": "n", "ប": "b",
    "ផ": "ph", "ព": "p", "ភ": "ph", "ម": "m", "យ": "y", "រ": "r", "ល": "l",
    "វ": "v", "ស": "s", "ហ": "h", "ឡ": "l", "អ": "",
}

# Dependent vowel -> (a-series reading, o-series reading). "" is the inherent vowel.
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

_TRUST = 0.7          # keep a learned spelling only with direct or >=2x aligned support
_ALIGN_WEIGHT = 0.35
_MAX_VARIANTS = 8     # cap on generated variants per word

# Common ways people re-spell the same sound (learned from verification batches), applied
# on top of the per-syllable options to widen coverage: aspiration is often dropped
# (phnaek/pnaek, phdol/pdol), ិ wavers e<->i (kech/kich), a coda "o" is often "or"
# (bonto/bontor). Each is tried once per candidate; results are scored low and capped.
_SUBSTITUTIONS = (("ph", "p"), ("th", "t"), ("kh", "k"))


def _is_cons(ch: str) -> bool:
    return 0x1780 <= ord(ch) <= 0x17A2


def _is_bare_final(kcc: str) -> bool:
    """A syllable that is a single consonant, optionally with ់ — a plain final/coda."""
    return (len(kcc) == 1 and _is_cons(kcc[0])) or (
        len(kcc) == 2 and _is_cons(kcc[0]) and ord(kcc[1]) == _BANTOC
    )


def _compose(kcc: str, force_series: int | None = None) -> str:
    """Build a syllable's spelling from the consonant + vowel tables (layer 3)."""
    chars = list(kcc)
    if chars and chars[0] in _INDEP:               # independent-vowel syllable
        rest = "".join(chars[1:]).replace("់", "")
        return _INDEP[chars[0]] + ("h" if "ះ" in rest else "")
    onset: list[str] = []
    i = 0
    while i < len(chars):
        if _is_cons(chars[i]):
            onset.append(chars[i])
            i += 1
        elif ord(chars[i]) == _COENG and i + 1 < len(chars) and _is_cons(chars[i + 1]):
            onset.append(chars[i + 1])
            i += 2
        else:
            break
    vowel = "".join(chars[i:]).replace("់", "").replace("៉", "").replace("៊", "")
    tail = ""
    if "ះ" in vowel:
        vowel, tail = vowel.replace("ះ", ""), "h"
    series = force_series or (2 if (onset and onset[0] in _SERIES_2) else 1)
    letters = "".join(_CONS.get(c, "") for c in onset)
    return letters + _VOW.get(vowel, ("", ""))[series - 1] + tail


def _best_affix(text: str, spellings: set[str], *, prefix: bool) -> str | None:
    best = None
    for s in spellings:
        if s and len(s) < len(text) and (text.startswith(s) if prefix else text.endswith(s)):
            if best is None or len(s) > len(best):
                best = s
    return best


class Romanizer:
    """Learns the romanization pattern from a vocabulary and applies it to any word."""

    def __init__(self, vocab: list[VocabEntry]) -> None:
        self.rules = self._build_rules(vocab)

    @staticmethod
    def _build_rules(vocab: list[VocabEntry]) -> dict[str, str]:
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

    def _coda(self, kcc: str, is_last: bool) -> list[str]:
        """Plausible spellings for a non-initial bare consonant (a syllable coda)."""
        c = kcc[0]
        if c == "រ":
            return ["", "r"] if is_last else ["r"]      # final រ silent; medial រ kept
        base = _FINAL.get(c, _CONS.get(c, ""))
        if base in ("s", "h"):                           # final ស/ះ waver s <-> h
            return ["s", "h"]
        return [base]

    def _options(self, kccs: list[str], i: int) -> list[str]:
        """Up to a few plausible spellings for syllable ``i`` of the word."""
        kcc = kccs[i]
        is_last = i == len(kccs) - 1
        if i > 0 and _is_bare_final(kcc):
            return self._coda(kcc, is_last)
        opts: list[str] = []
        if kcc in self.rules:
            opts.append(self.rules[kcc])
        opts.append(_compose(kcc, 1))                    # a-series reading
        opts.append(_compose(kcc, 2))                    # o-series reading
        seen: set[str] = set()
        return [o for o in opts if not (o in seen or seen.add(o))][:3]

    def romanize(self, khmer: str) -> str:
        """The single best-guess Sing Khmer spelling."""
        kccs = segment(khmer)
        out: list[str] = []
        for i, kcc in enumerate(kccs):
            if i > 0 and _is_bare_final(kcc):
                if kcc[0] == "រ" and i != len(kccs) - 1:
                    out.append("r")                      # medial រ kept
                else:
                    out.append(_FINAL.get(kcc[0], _CONS.get(kcc[0], "")))
            elif kcc in self.rules:
                out.append(self.rules[kcc])
            else:
                out.append(_compose(kcc))
        return "".join(out)

    @staticmethod
    def _respellings(word: str) -> list[str]:
        """One-step re-spellings of a candidate (drop aspiration, e<->i, coda o<->or)."""
        out: list[str] = []
        for a, b in _SUBSTITUTIONS:
            if a in word:
                out.append(word.replace(a, b))
        if "e" in word:
            out.append(word.replace("e", "i", 1))
        if "i" in word:
            out.append(word.replace("i", "e", 1))
        if word.endswith("or"):
            out.append(word[:-1])                        # ...or -> ...o
        elif word.endswith("o"):
            out.append(word + "r")                       # ...o  -> ...or
        return out

    def variants(self, khmer: str, cap: int = _MAX_VARIANTS) -> list[str]:
        """A small set of plausible spellings (best first), for the generated layer."""
        kccs = segment(khmer)
        if not kccs:
            return []
        results = [""]
        for i in range(len(kccs)):
            results = [r + o for r in results for o in self._options(kccs, i)]
            if len(results) > 40:                        # bound combinatorial blow-up
                results = results[:40]
        primary = self.romanize(khmer)
        ordered = [primary] + [r for r in results if r != primary]
        ordered += [rs for s in ordered for rs in self._respellings(s)]  # widen
        seen: set[str] = set()
        out: list[str] = []
        for s in ordered:
            if s and s not in seen:
                seen.add(s)
                out.append(s)
            if len(out) >= cap:
                break
        return out
