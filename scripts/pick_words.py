#!/usr/bin/env python3
"""Pick common Khmer words NOT yet in the vocabulary, to verify and add.

Reads a frequency-ranked Khmer word list (word<TAB>count per line, most-frequent first —
e.g. SEALang's `seafreq.txt` from sbbic/khmerlbdict) and keeps the everyday, conversational
words: real 2-syllable content words, most-frequent first, excluding anything already in the
DB. Prints `khmer<TAB>predicted-spelling` so you can eyeball or pipe into a sheet.

Why the filter: raw frequency lists are full of bound fragments (សម, រប) that are frequent as
*parts* of words but never typed alone. Requiring exactly two syllables, length >= 4, and a
vowel-or-subscript keeps real words.

Usage:
    PYTHONPATH=src python scripts/pick_words.py seafreq.txt            # top 150
    PYTHONPATH=src python scripts/pick_words.py seafreq.txt 300        # top 300
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.kcc import segment  # noqa: E402
from sing_khmer_engine.lookup import Engine  # noqa: E402


def _khmer_only(w: str) -> bool:
    return bool(w) and all(0x1780 <= ord(c) <= 0x17FF for c in w)


def _has_vowel_or_cluster(w: str) -> bool:
    return any(
        0x17B6 <= ord(c) <= 0x17C8 or 0x17A5 <= ord(c) <= 0x17B3 or ord(c) == 0x17D2
        for c in w
    )


def pick(freq_path: Path, limit: int, db: set[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in freq_path.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        word = line.split("\t")[0].strip()
        if (
            not _khmer_only(word) or word in db or word in seen
            or len(word) < 4 or len(segment(word)) != 2
            or not _has_vowel_or_cluster(word)
        ):
            continue
        seen.add(word)
        out.append(word)
        if len(out) >= limit:
            break
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    freq_path = Path(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    eng = Engine()
    db = {e.khmer for e in eng.vocab}
    for w in pick(freq_path, limit, db):
        print(f"{w}\t{eng.romanizer.romanize(w)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
