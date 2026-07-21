#!/usr/bin/env python3
"""Print each vocabulary word broken into Khmer Character Clusters (step 1.3 demo).

Usage (from the project root):
    PYTHONPATH=src python scripts/show_kccs.py
"""

import sys
from pathlib import Path

# Make `sing_khmer_engine` importable when run directly (mirrors pytest's pythonpath).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.kcc import segment  # noqa: E402
from sing_khmer_engine.vocabulary import load  # noqa: E402


def main() -> None:
    entries = load()
    width = max((len(e.khmer) for e in entries), default=0)
    print(f"KCC breakdown for {len(entries)} vocabulary word(s):\n")
    for e in entries:
        kccs = segment(e.khmer)
        print(f"  {e.khmer:<{width}}  →  {' · '.join(kccs)}   ({len(kccs)} KCC)")


if __name__ == "__main__":
    main()
