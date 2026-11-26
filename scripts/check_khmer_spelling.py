#!/usr/bin/env python3
"""Check the KHMER spelling of curated words against the Chuon Nath dictionary.

A word passes if it is a Chuon Nath headword (ericvida/khmer-dictionary-spice,
kh_dictionary_words.csv), or in the SBBIC spelling list from the same repo (modern words),
or splits completely into such words (phrases like ខ្ញុំស្រឡាញ់អ្នក). Everything else is
listed with the closest dictionary spelling, for a human to decide: nothing is changed.
Slang, names and loanwords (ហ្គេម, អូខេ) fail legitimately — that is expected.

Usage:
    PYTHONPATH=src python scripts/check_khmer_spelling.py CHUON_NATH_WORDS SBBIC_WORDS \\
        [--vocab data/vocabulary.csv] [--out data/review/spelling_check.csv]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_general_wordlist import clean  # noqa: E402
from sing_khmer_engine.fuzzy import levenshtein  # noqa: E402
from sing_khmer_engine.vocabulary import DEFAULT_VOCAB_PATH, load  # noqa: E402


def splits_into(word: str, known: set[str], longest: int) -> bool:
    """True if `word` is a run of known words, each at least two characters."""
    ok = [True] + [False] * len(word)
    for i in range(1, len(word) + 1):
        for j in range(max(0, i - longest), i - 1):
            if ok[j] and word[j:i] in known:
                ok[i] = True
                break
    return ok[-1]


def nearest(word: str, known_by_len: dict[int, list[str]], limit: int = 2) -> list[str]:
    best: list[tuple[int, str]] = []
    for n in range(max(1, len(word) - 2), len(word) + 3):
        for k in known_by_len.get(n, ()):
            d = levenshtein(word, k)
            if d <= 2:
                best.append((d, k))
    return [k for _, k in sorted(best)[:limit]]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("chuon_nath", type=Path)
    p.add_argument("sbbic", type=Path)
    p.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB_PATH)
    p.add_argument("--out", type=Path, default=ROOT / "data" / "review" / "spelling_check.csv")
    a = p.parse_args()

    chuon = {clean(x) for x in a.chuon_nath.read_text(encoding="utf-8").splitlines()} - {""}
    sbbic = {clean(x.split("/")[0])
             for x in a.sbbic.read_text(encoding="utf-8-sig").splitlines()} - {""}
    known = chuon | sbbic
    longest = max(map(len, known))
    by_len: dict[int, list[str]] = {}
    for k in chuon:                         # suggest Chuon Nath spellings first
        by_len.setdefault(len(k), []).append(k)

    flagged = []
    vocab = load(a.vocab)
    for e in vocab:
        word = clean(e.khmer)
        if word in known or splits_into(word, known, longest):
            continue
        flagged.append({
            "khmer": e.khmer,
            "spellings": ", ".join(e.romanizations),
            "closest_chuon_nath": " / ".join(nearest(word, by_len)),
            "fix_to": "",
            "notes": e.notes,
        })
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["khmer", "spellings", "closest_chuon_nath", "fix_to",
                                          "notes"], lineterminator="\n")
        w.writeheader()
        w.writerows(flagged)
    print(f"{len(vocab)} words checked; {len(flagged)} not found in Chuon Nath/SBBIC "
          f"-> {a.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
