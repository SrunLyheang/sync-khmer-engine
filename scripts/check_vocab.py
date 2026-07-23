#!/usr/bin/env python3
"""Lint data/vocabulary.csv for suspicious rows (Phase 4).

The loader already enforces the schema (required columns, frequency range, boolean
is_slang, unique khmer). This lint catches *content* problems the loader can't — the
kind that quietly produce bad spellings:

  ERROR  non-ASCII letters in a romanization ("café" instead of "cafe")
  ERROR  stray punctuation in a romanization ("kort." or 'p"o' — an apostrophe,
         used for the អ onset like s'aek, is allowed; other punctuation is not)
  ERROR  zero-width or control characters hiding in a cell
  WARN   duplicate alternatives in one row (redundant)
  WARN   a "+" multi-word spelling whose parts are ALSO listed as single
         alternatives of the same word — a likely space-vs-"+" mix-up (two
         alternatives mistakenly joined into one multi-word key)

Usage (from the project root):
    PYTHONPATH=src python scripts/check_vocab.py           # lint the bundled file
    PYTHONPATH=src python scripts/check_vocab.py path.csv  # lint another file

Exit status is non-zero if any ERROR is found, so it can gate CI.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sing_khmer_engine.vocabulary import DEFAULT_VOCAB_PATH, load, parse_romanizations  # noqa: E402

_ZERO_WIDTH = {"​", "‌", "‍", "﻿"}
# A parsed alternative: latin letters, spaces (from "+"), and the apostrophe used
# to mark the អ onset (s'aek, p'aem). Nothing else.
_ALLOWED_CHAR = re.compile(r"[a-z' ]")
_ALLOWED = re.compile(r"^[a-z' ]+$")


def _raw_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def check(path: Path) -> list[tuple[str, str, str]]:
    """Return a list of (level, khmer, message) issues. level is ERROR or WARN."""
    issues: list[tuple[str, str, str]] = []
    load(path)                                 # validates schema first (may raise)

    for raw in _raw_rows(path):
        khmer = (raw.get("khmer") or "").strip()
        cell = raw.get("romanizations") or ""

        if any(ch in _ZERO_WIDTH or (ord(ch) < 32 and ch not in "\t") for ch in cell):
            issues.append(("ERROR", khmer, "romanizations contain a zero-width/control character"))

        alts = parse_romanizations(cell)
        singles = {a for a in alts if " " not in a}
        for alt in alts:
            if not _ALLOWED.match(alt):
                bad = sorted({ch for ch in alt if not _ALLOWED_CHAR.match(ch)})
                issues.append(("ERROR", khmer,
                               f"spelling {alt!r} has unexpected characters {bad}"))
            elif " " in alt and all(p in singles for p in alt.split(" ")):
                # a "+" spelling whose parts are ALSO single alternatives of THIS word
                issues.append(("WARN", khmer,
                               f"multi-word spelling {alt!r}: its parts are also single "
                               f"alternatives here — likely a space-vs-'+' mix-up"))

        dupes = [a for a, n in Counter(alts).items() if n > 1]
        if dupes:
            issues.append(("WARN", khmer, f"duplicate alternatives: {dupes}"))

    return issues


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VOCAB_PATH
    issues = check(path)
    errors = [i for i in issues if i[0] == "ERROR"]
    for level, khmer, msg in issues:
        print(f"  {level:5} {khmer!s:8} {msg}")
    total = len(load(path))
    print(f"\nchecked {total} rows: {len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
