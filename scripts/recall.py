#!/usr/bin/env python3
"""Recall: if a real spelling weren't stored, would the engine still find the word?

Exact-match accuracy is the wrong metric now — there is no one "correct" Sing Khmer
spelling. What matters is **recall**: when someone types a spelling we didn't explicitly
store, does the engine still land on the right Khmer word, via the generated variant layer
or fuzzy matching?

For every collected spelling of every word, this checks whether that word is still reachable
from that spelling *without counting the spelling itself* — i.e. via another stored spelling,
a generated variant, or a fuzzy match to one of those. That simulates the spelling being
"unseen" and reports the fraction still covered.

Usage:
    PYTHONPATH=src python scripts/recall.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.fuzzy import within  # noqa: E402
from sing_khmer_engine.lookup import Engine  # noqa: E402


def _threshold(key: str) -> int:
    return 1 if len(key) <= 3 else 2


def main() -> int:
    eng = Engine()

    # For each Khmer word, the set of index keys that map to it (collected + generated).
    keys_of: dict[str, list[str]] = {}
    for key, cands in eng.index.items():
        for c in cands:
            keys_of.setdefault(c.khmer, []).append(key)

    covered = missed = 0
    misses: list[tuple[str, str]] = []
    for e in eng.vocab:
        for spelling in e.romanizations:
            s = spelling.replace(" ", "")            # a real spelling someone typed
            # reachable if any OTHER key of this word equals or is fuzzy-close to s
            others = [k for k in keys_of.get(e.khmer, []) if k != spelling and k != s]
            hit = any(k == s or within(s, k, _threshold(s)) is not None for k in others)
            if hit:
                covered += 1
            else:
                missed += 1
                if len(misses) < 20:
                    misses.append((e.khmer, spelling))
    total = covered + missed
    print(f"index keys: {len(eng.index)}")
    print(f"recall (real spelling still finds its word if unseen): "
          f"{covered}/{total} = {100 * covered / total:.0f}%")
    print("\nsample misses (spellings only reachable by being stored verbatim):")
    for kh, sp in misses:
        print(f"  {kh:10} {sp!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
