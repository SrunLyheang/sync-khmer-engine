#!/usr/bin/env python3
"""Merge the words you taught the Mac keyboard into data/vocabulary.csv.

The Mac keyboard keeps the words you add in
    ~/Library/Application Support/SingKhmer/my_words.txt
(one per line: the spelling, then the Khmer). They work on your Mac straight away, but
only there. This script copies them into the shared dictionary so the web app, and anyone
else who builds the keyboard, gets them too:

  - a Khmer word already in the dictionary gains any spelling it does not have yet;
  - a new Khmer word is added as a new row (frequency 3, tagged in `notes`).

Nothing is removed and existing rows are otherwise left alone. Review the result with
`git diff data/vocabulary.csv` before committing.

Usage (from the project root, on the Mac):
    python3 scripts/import_mac_words.py                 # the default my_words.txt
    python3 scripts/import_mac_words.py path/to/file    # any file in the same format
    python3 scripts/import_mac_words.py --dry-run       # show what would change
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sing_khmer_engine.vocabulary import DEFAULT_VOCAB_PATH, load, parse_romanizations  # noqa: E402

DEFAULT_WORDS_PATH = Path.home() / "Library" / "Application Support" / "SingKhmer" / "my_words.txt"
NEW_WORD_FREQUENCY = "3"
NEW_WORD_NOTE = "(from Mac keyboard)"

_KHMER = re.compile(r"[ក-៿᧠-᧿]")
_LATIN = re.compile(r"[a-z' ]+")


def parse_words(text: str) -> list[tuple[str, str]]:
    """(spelling, khmer) pairs from a my_words.txt. Same rules as the Swift parser
    (`UserWord.parse` in macos/SingKhmer/Sources/SingKhmerCore/Learning.swift)."""
    words: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _KHMER.search(line)
        if match is None:
            continue
        latin = " ".join(line[: match.start()].strip(" \t=,:").lower().split())
        khmer = line[match.start():].strip()
        if latin and khmer and _LATIN.fullmatch(latin) and (latin, khmer) not in words:
            words.append((latin, khmer))
    return words


def merge(csv_text: str, words: list[tuple[str, str]], *,
          note: str | dict[str, str] = NEW_WORD_NOTE) -> tuple[str, list[str]]:
    """Apply `words` to the vocabulary CSV text. Returns (new text, change summary).

    `note` goes in the `notes` column of each NEW row: one string for all, or a
    {khmer: note} dict (missing keys fall back to NEW_WORD_NOTE)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    fieldnames = reader.fieldnames or ["khmer", "frequency", "is_slang", "romanizations", "notes"]
    by_khmer = {(row.get("khmer") or "").strip(): row for row in rows}

    summary: list[str] = []
    for latin, khmer in words:
        cell = latin.replace(" ", "+")            # multi-word spellings use + in the CSV
        row = by_khmer.get(khmer)
        if row is None:
            row = {name: "" for name in fieldnames}
            row.update(khmer=khmer, frequency=NEW_WORD_FREQUENCY, is_slang="false",
                       romanizations=cell,
                       notes=note if isinstance(note, str) else note.get(khmer, NEW_WORD_NOTE))
            rows.append(row)
            by_khmer[khmer] = row
            summary.append(f"new word   {khmer}  {latin}")
            continue
        existing = row.get("romanizations") or ""
        if latin in parse_romanizations(existing):
            continue
        row["romanizations"] = f"{existing}, {cell}" if existing.strip() else cell
        summary.append(f"spelling   {khmer}  + {latin}")

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue(), summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("words", nargs="?", type=Path, default=DEFAULT_WORDS_PATH,
                        help="my_words.txt to import (default: the Mac keyboard's own file)")
    parser.add_argument("--dry-run", action="store_true", help="show changes without writing")
    args = parser.parse_args()

    if not args.words.exists():
        sys.exit(f"{args.words} not found. Add a word from the Sing Khmer menu "
                 "(Edit My Words) first, or pass the file's path.")
    words = parse_words(args.words.read_text(encoding="utf-8"))
    original = DEFAULT_VOCAB_PATH.read_text(encoding="utf-8")
    updated, summary = merge(original, words)

    if not summary:
        print(f"{len(words)} of your words checked; the dictionary already has all of them.")
        return
    print("\n".join(summary))
    if args.dry_run:
        print(f"\n(dry run) {len(summary)} change(s) not written.")
        return
    DEFAULT_VOCAB_PATH.write_text(updated, encoding="utf-8")
    load()                                        # fail loudly if the file is no longer valid
    print(f"\n{len(summary)} change(s) written to {DEFAULT_VOCAB_PATH.relative_to(ROOT)}. "
          "Review with: git diff data/vocabulary.csv")


if __name__ == "__main__":
    main()
