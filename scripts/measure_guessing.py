#!/usr/bin/env python3
"""How well does the engine guess words it has no spelling for? The yardstick for
Khmer-only words (data/wordlist_general.csv) and for every guessing-rule change.

Three numbers; a change is only kept if it does not make (2) or (3) worse:

  1. guess    Hide the real spellings of a fifth of the curated words (5 folds, so every
              word is hidden once), rebuild the engine, type each hidden spelling as one
              token, and ask: is the word first (top1) / in the top 3 (top3)?
              The answer key is YOUR spellings from vocabulary.csv, not anyone's guesses.
  2. english  English words the keyboard's own list does not protect (from a subtitle
              frequency list): are they left as typed? Khmer-only words make this worse,
              because every new guess is a chance to swallow an English word.
  3. known    Every collected spelling, with nothing hidden: is its own word still first?
              (New words must not steal spellings you already use.)

Usage:
    PYTHONPATH=src python scripts/measure_guessing.py --english path/to/en_50k.txt
    ... --review data/review/movie_words.csv   # also score my researched spellings
    ... --misses 20                            # print some guesses that failed
The English list is hermitdave/FrequencyWords content/2018/en/en_50k.txt (MIT/CC-BY-SA);
it is not shipped in the repo, so pass its path (the English number is skipped without it).
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sing_khmer_engine.english import load_english  # noqa: E402
from sing_khmer_engine.lookup import Engine  # noqa: E402
from sing_khmer_engine.vocabulary import load, parse_romanizations  # noqa: E402

FOLDS = 5
SEED = 7


def found(engine: Engine, text: str, khmer: str) -> tuple[bool, bool]:
    """(first, in top 3) for `text` typed as one token."""
    first = engine.convert_sentence_text(text).replace(" ", "") == khmer
    if first:
        return True, True
    words = [w for w in engine.decode(text) if not w.space and w.surface.strip()]
    if len(words) == 1 and any(c.khmer == khmer for c in words[0].candidates[:3]):
        return False, True
    return False, any(r.replace(" ", "") == khmer for r in engine.readings(text, k=3))


def teach_hit(engine: Engine, text: str, khmer: str) -> bool:
    """The Mac keyboard's pick-to-teach: when nothing matches, the loose guesses it offers
    (Engine.convert, not strict) include the word in their top 3."""
    if engine.convert_sentence_text(text) != text:
        return False
    return khmer in [c.khmer for c in engine.convert(text, limit=3) if c.source != "english"]


def guess_score(vocab, misses: list | None = None, folds: int = FOLDS,
                teach: list | None = None) -> tuple[int, int, int]:
    curated = [i for i, e in enumerate(vocab) if e.romanizations]
    random.Random(SEED).shuffle(curated)
    n = top1 = top3 = 0
    for fold in range(folds):
        hidden = set(curated[fold::FOLDS])
        trial = [dataclasses.replace(e, romanizations=()) if i in hidden else e
                 for i, e in enumerate(vocab)]
        engine = Engine(trial)
        for i in hidden:
            e = vocab[i]
            for spelling in e.romanizations:
                a, b = found(engine, spelling.replace(" ", ""), e.khmer)
                n, top1, top3 = n + 1, top1 + a, top3 + b
                if teach is not None:
                    teach.append(b or teach_hit(engine, spelling.replace(" ", ""), e.khmer))
                if misses is not None and not b:
                    misses.append((spelling, e.khmer,
                                   engine.convert_sentence_text(spelling.replace(" ", ""))))
    return n, top1, top3


def english_words(path: Path, protected: frozenset, count: int = 3000) -> list[str]:
    words = []
    for rank, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        w = line.split()[0] if line.strip() else ""
        if 1500 <= rank and len(w) >= 3 and w.isascii() and w.isalpha() and w not in protected:
            words.append(w)
    step = max(1, len(words) // count)
    return words[::step][:count]


def english_score(engine: Engine, words: list[str]) -> tuple[int, int, list[str]]:
    eaten = [w for w in words if engine.convert_sentence_text(w) != w]
    return len(words), len(words) - len(eaten), eaten


def known_score(engine: Engine, vocab) -> tuple[int, int]:
    n = ok = 0
    for e in vocab:
        for spelling in e.romanizations:
            n += 1
            ok += engine.convert_sentence_text(spelling.replace(" ", "")).replace(" ", "") == e.khmer \
                or engine.convert_sentence_text(spelling).replace(" ", "") == e.khmer
    return n, ok


def review_score(engine: Engine, path: Path) -> tuple[int, int, int]:
    n = top1 = top3 = 0
    for r in csv.DictReader(path.open(encoding="utf-8")):
        for s in parse_romanizations(r.get("spellings", ""))[:1]:
            a, b = found(engine, s.replace(" ", ""), r["khmer"])
            n, top1, top3 = n + 1, top1 + a, top3 + b
    return n, top1, top3


def pct(a: int, n: int) -> str:
    return f"{100 * a / n:5.1f}%" if n else "  n/a"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--english", type=Path, help="en_50k.txt from hermitdave/FrequencyWords")
    p.add_argument("--review", type=Path, help="review sheet whose words to score Khmer-only")
    p.add_argument("--misses", type=int, default=0, help="print this many failed guesses")
    p.add_argument("--quick", action="store_true", help="hide one fold only (a fifth of the words)")
    a = p.parse_args()

    vocab = load()
    misses: list = [] if a.misses else None
    teach: list = []
    n, t1, t3 = guess_score(vocab, misses, 1 if a.quick else FOLDS, teach)
    print(f"guess    n={n:5}  top1 {pct(t1, n)}  top3 {pct(t3, n)}   (your spellings, hidden)")
    print(f"  +teach         top3 {pct(sum(teach), n)}   (Mac keyboard: plus pick-to-teach guesses)")

    engine = Engine(vocab)
    if a.english:
        n, ok, eaten = english_score(engine, english_words(a.english, load_english()))
        print(f"english  n={n:5}  left alone {pct(ok, n)}   e.g. {', '.join(eaten[:8])}")
    n, ok = known_score(engine, vocab)
    print(f"known    n={n:5}  still first {pct(ok, n)}")
    if a.review:
        n, t1, t3 = review_score(engine, a.review)
        print(f"review   n={n:5}  top1 {pct(t1, n)}  top3 {pct(t3, n)}   (my spellings)")
    for s, k, got in (misses or [])[: a.misses]:
        print(f"  miss  {s:14} want {k:12} got {got}")


if __name__ == "__main__":
    main()
