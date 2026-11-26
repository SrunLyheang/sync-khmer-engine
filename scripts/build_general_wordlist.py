#!/usr/bin/env python3
"""Build data/wordlist_general.csv: Khmer words with NO Sing Khmer spelling.

The engine guesses spellings for these (see romanizer.py) and ranks them below every word
in vocabulary.csv. The Mac keyboard's pick-to-teach turns a guess you pick into a real
spelling in my_words.txt.

Where the words come from:
  - the most frequent words of the SEALang frequency list, as cleaned up in
    sbbic/khmerlbdict (src/seafreq.txt, MIT; SEALang's own terms are not stated, so check
    them before distributing this list publicly);
  - kept only if the spelling is checked: a headword of the Chuon Nath dictionary
    (ericvida/khmer-dictionary-spice, kh_dictionary_words.csv, LGPL 2.1), or — for modern
    words that 1967 dictionary lacks (កម្ពុជា, ប្រើប្រាស់) — in the SBBIC spelling list from
    the same repo (SBBICkm_KH.txt), as long as it is not a fragment;
  - fragments are dropped: 1-3 bare consonants with no vowel or mark (សម, រប, ថល), which
    the frequency list's word splitting left behind;
  - plus the words of a review sheet (data/review/*.csv) that are not in vocabulary.csv yet,
    so researched words work as guesses before their spellings are reviewed.
Words already in vocabulary.csv are skipped.

Usage:
    python scripts/build_general_wordlist.py SEAFREQ CHUON_NATH_WORDS SBBIC_WORDS \\
        [--top 5000] [--review data/review/movie_words.csv]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sing_khmer_engine.vocabulary import DEFAULT_GENERAL_PATH, load  # noqa: E402

_INVISIBLE = re.compile(r"[\u200b-\u200f\ufeff\"' ]")
_KHMER_WORD = re.compile(r"^[\u1780-\u17ff]+$")
_BARE_CONSONANTS = re.compile(r"^[\u1780-\u17a2]{1,3}$")


def is_fragment(word: str) -> bool:
    """សម, រប, ថល: consonants only, no vowel, subscript or mark."""
    return bool(_BARE_CONSONANTS.match(word))


def clean(word: str) -> str:
    return _INVISIBLE.sub("", unicodedata.normalize("NFC", word.strip()))


def frequency(rank: int) -> int:
    """1-3: always below the curated words that matter (which go up to 5)."""
    return 3 if rank < 1000 else 2 if rank < 3000 else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("seafreq", type=Path)
    p.add_argument("chuon_nath", type=Path)
    p.add_argument("sbbic", type=Path)
    p.add_argument("--top", type=int, default=5000, help="how many frequency-list words to scan")
    p.add_argument("--review", type=Path, action="append", default=[])
    a = p.parse_args()

    headwords = {clean(line) for line in a.chuon_nath.read_text(encoding="utf-8").splitlines()}
    sbbic = {clean(line.split("/")[0])
             for line in a.sbbic.read_text(encoding="utf-8-sig").splitlines()}
    have = {e.khmer for e in load()}
    rows: dict[str, tuple[int, str]] = {}
    scanned = not_in_dictionary = 0
    for rank, line in enumerate(a.seafreq.read_text(encoding="utf-8").splitlines()[: a.top]):
        if not line.strip():
            continue
        word = clean(line.split("\t")[0])
        scanned += 1
        if not _KHMER_WORD.match(word) or word in have or word in rows:
            continue
        if is_fragment(word):
            not_in_dictionary += 1
            continue
        if word in headwords:
            rows[word] = (frequency(rank), "seafreq+chuonnath")
        elif word in sbbic:
            rows[word] = (frequency(rank), "seafreq+sbbic")
        else:
            not_in_dictionary += 1
    from_review = 0
    for path in a.review:
        for r in csv.DictReader(path.open(encoding="utf-8")):
            word = clean(r.get("khmer", ""))
            if word and word not in have and word not in rows:
                rows[word] = (2, f"review:{path.name}")
                from_review += 1

    with DEFAULT_GENERAL_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["khmer", "frequency", "source"])
        for word, (freq, source) in rows.items():
            w.writerow([word, freq, source])
    print(f"scanned {scanned} frequency-list words; {not_in_dictionary} fragments or "
          f"unchecked spellings (dropped); {len(rows) - from_review} kept + {from_review} from review sheets "
          f"-> {DEFAULT_GENERAL_PATH.relative_to(ROOT)} ({len(rows)} words)")


if __name__ == "__main__":
    main()
