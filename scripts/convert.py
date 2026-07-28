#!/usr/bin/env python3
"""Interactive Sing Khmer -> Khmer converter (steps 1.6-1.8 demo).

Handles single words AND whole sentences (split on spaces).

Usage (from the project root):
    PYTHONPATH=src python scripts/convert.py                 # interactive prompt
    PYTHONPATH=src python scripts/convert.py jg              # one word -> ranked candidates
    PYTHONPATH=src python scripts/convert.py nh sl bong      # a sentence -> converted + breakdown

NOTE: terminals often can't render Khmer script correctly (the letters may look
broken). That's a terminal font limitation, not a data problem — run the web app
in a browser to see it render properly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.lookup import Engine  # noqa: E402

_TAG = {"collected": "", "generated": " (auto)", "fuzzy": " (~typo)"}


def show_word(engine: Engine, word: str) -> None:
    """Print the ranked candidates for a single spelling."""
    results = engine.convert(word)
    if not results:
        print(f"  {word!r} -> (no match found)")
        return
    parts = [f"{i}. {c.khmer} (score {c.score}{_TAG.get(c.source, '')})"
             for i, c in enumerate(results, 1)]
    print(f"  {word!r} -> " + "   ".join(parts))


def show_sentence(engine: Engine, text: str) -> None:
    """Print a full message conversion plus a per-segment breakdown."""
    segments = engine.decode(text)
    print("  " + engine.convert_sentence_text(text))
    print("  ── segment by segment ──")
    for w in segments:
        if w.matched:
            alts = "  ".join(f"{c.khmer}{_TAG.get(c.source, '')}" for c in w.candidates)
            print(f"    {w.surface!r} -> {alts}")
        else:
            print(f"    {w.surface!r} -> (no match — kept as-is)")


def handle(engine: Engine, text: str) -> None:
    # The decoder handles single words, spaced sentences, AND no-space input.
    if " " in text.strip():
        show_sentence(engine, text)
    else:
        show_word(engine, text)


def main() -> None:
    print("Loading engine...")
    engine = Engine()
    print(f"Ready — {len(engine.index)} spellings indexed."
          " (auto) = generated, (~typo) = fuzzy match\n")

    args = sys.argv[1:]
    if args:
        handle(engine, " ".join(args))
        return

    print("Type a word or a sentence and press Enter (blank line or Ctrl-D to quit).")
    while True:
        try:
            text = input("Sing Khmer > ").strip()
        except EOFError:
            print()
            break
        if not text:
            break
        handle(engine, text)


if __name__ == "__main__":
    main()
