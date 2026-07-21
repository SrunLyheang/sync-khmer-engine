#!/usr/bin/env python3
"""Interactive Sing Khmer -> Khmer converter (steps 1.6 + 1.7 demo).

Usage (from the project root):
    PYTHONPATH=src python scripts/convert.py            # interactive prompt
    PYTHONPATH=src python scripts/convert.py jg nh sl   # one-shot for given words
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.lookup import Engine  # noqa: E402


_TAG = {"collected": "", "generated": " (auto)", "fuzzy": " (~typo)"}


def show(engine: Engine, word: str) -> None:
    results = engine.convert(word)
    if not results:
        print(f"  {word!r:12} -> (no match found)")
        return
    parts = [
        f"{i}. {c.khmer} (score {c.score}{_TAG.get(c.source, '')})"
        for i, c in enumerate(results, 1)
    ]
    print(f"  {word!r:12} -> " + "   ".join(parts))


def main() -> None:
    print("Loading engine...")
    engine = Engine()
    print(f"Ready — {len(engine.index)} spellings indexed."
          " (auto) = generated spelling, (~typo) = fuzzy match\n")

    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        for word in args:
            show(engine, word)
        return

    print("Type a Sing Khmer spelling and press Enter (blank line or Ctrl-D to quit).")
    while True:
        try:
            word = input("Sing Khmer > ").strip()
        except EOFError:
            print()
            break
        if not word:
            break
        show(engine, word)


if __name__ == "__main__":
    main()
