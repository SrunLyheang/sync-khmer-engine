#!/usr/bin/env python3
"""Diagnose why Sing Khmer input does or doesn't convert.

For each word (or each word in a sentence), reports one of:
  EXACT      - matched a spelling exactly as collected
  FUZZY      - matched within the fuzzy edit-distance threshold
  NO MATCH   - nothing close enough; shows the single nearest known spelling
               and its raw edit distance, so you can tell "this word truly
               isn't in the vocabulary yet" from "it's in there, but this
               spelling is just too far off".

Usage (from the project root):
    PYTHONPATH=src python scripts/diagnose.py                    # interactive
    PYTHONPATH=src python scripts/diagnose.py srolan teuk zzzzq  # one-shot words
    PYTHONPATH=src python scripts/diagnose.py "nh sl bong te"    # one-shot sentence (quoted)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.lookup import Engine  # noqa: E402


def report(engine: Engine, word: str) -> None:
    d = engine.diagnose(word)
    if d.outcome == "exact":
        top = ", ".join(f"{c.khmer}({c.score})" for c in d.candidates[:3])
        print(f"  EXACT     {word!r:14} -> {top}")
    elif d.outcome == "fuzzy":
        top = ", ".join(f"{c.khmer}({c.score})" for c in d.candidates[:3])
        print(f"  FUZZY     {word!r:14} -> {top}")
    else:
        if d.closest_key is not None:
            print(f"  NO MATCH  {word!r:14} -> nearest known spelling is "
                  f"{d.closest_key!r} ({d.closest_distance} edits away — too far)")
        else:
            print(f"  NO MATCH  {word!r:14} -> vocabulary is empty?!")


def main() -> None:
    print("Loading engine...")
    engine = Engine()
    print(f"Ready — {len(engine.index)} spellings indexed.\n")

    args = sys.argv[1:]
    if args:
        words = " ".join(args).split()
        for w in words:
            report(engine, w)
        return

    print("Type a word (or a sentence) and press Enter (blank line or Ctrl-D to quit).")
    while True:
        try:
            text = input("Diagnose > ").strip()
        except EOFError:
            print()
            break
        if not text:
            break
        for w in text.split():
            report(engine, w)


if __name__ == "__main__":
    main()
