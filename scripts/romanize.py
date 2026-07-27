#!/usr/bin/env python3
"""CLI for the Khmer -> Sing Khmer romanizer (see sing_khmer_engine.romanizer).

Usage:
    PYTHONPATH=src python scripts/romanize.py ក្តី ខ្មៅ            # words as arguments
    PYTHONPATH=src python scripts/romanize.py --table words.txt    # markdown table from a file
    PYTHONPATH=src python scripts/romanize.py --variants ក្តៅ      # show the variant set
    echo "ក្តី" | PYTHONPATH=src python scripts/romanize.py        # from stdin
    PYTHONPATH=src python scripts/romanize.py --accuracy           # round-trip score on the DB
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.romanizer import Romanizer  # noqa: E402
from sing_khmer_engine.vocabulary import load  # noqa: E402


def accuracy(vocab, rom: Romanizer) -> tuple[int, int]:
    """Round-trip: how many known words regenerate to a spelling the user actually typed."""
    hit = total = 0
    for e in vocab:
        if not e.romanizations:
            continue
        total += 1
        if rom.romanize(e.khmer) in {r.replace(" ", "") for r in e.romanizations}:
            hit += 1
    return hit, total


def main() -> int:
    args = sys.argv[1:]
    vocab = load()
    rom = Romanizer(vocab)

    if "--accuracy" in args:
        hit, total = accuracy(vocab, rom)
        print(f"round-trip exact match on the DB: {hit}/{total} = {100 * hit / total:.0f}%")
        return 0

    show_variants = "--variants" in args
    table = "--table" in args
    args = [a for a in args if a not in ("--table", "--variants")]
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
            print(f"| {w} | `{rom.romanize(w)}`{note} | |")
    elif show_variants:
        for w in words:
            print(f"{w}\t{', '.join(rom.variants(w))}")
    else:
        for w in words:
            print(f"{w}\t{rom.romanize(w)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
