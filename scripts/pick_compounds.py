#!/usr/bin/env python3
"""Pick Khmer COMPOUND words that split into words already in the DB.

Khmer compounds are known words joined (ពាក់កណ្ដាល = ពាក់ + កណ្ដាល), so their spelling can be
built from the parts' already-verified spellings. This scans a frequency-ranked wordlist
(SEALang `seafreq.txt`) for frequent words NOT in the DB that split cleanly into known parts,
and romanizes each from those parts — a high-yield, high-quality way to grow the vocabulary.

Prints `khmer<TAB>predicted-spelling<TAB>part1+part2...` so the guesses can be verified before
being added to the DB.

Usage:
    PYTHONPATH=src python scripts/pick_compounds.py seafreq.txt          # top 150
    PYTHONPATH=src python scripts/pick_compounds.py seafreq.txt 300      # top 300
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.lookup import Engine  # noqa: E402


def _khmer_only(w: str) -> bool:
    return bool(w) and all(0x1780 <= ord(c) <= 0x17FF for c in w)


def pick(freq_path: Path, limit: int, eng: Engine) -> list[tuple[str, list[str]]]:
    db = {e.khmer for e in eng.vocab}
    out: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for line in freq_path.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        word = line.split("\t")[0].strip()
        if not _khmer_only(word) or word in db or word in seen:
            continue
        parts = eng.romanizer.split_compound(word)
        if parts:                                        # splits into >=2 known DB words
            seen.add(word)
            out.append((word, parts))
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
    for word, parts in pick(freq_path, limit, eng):
        print(f"{word}\t{eng.romanizer.romanize(word)}\t{'+'.join(parts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
