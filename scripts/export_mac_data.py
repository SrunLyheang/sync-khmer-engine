#!/usr/bin/env python3
"""Export the engine's runtime data for the macOS input method (macos/SingKhmer).

The Mac app does not run Python. Everything that is deterministic (vocabulary loading,
KCC segmentation, the romanizer, building the reverse index) runs here, once, and is
written to a single JSON file the app bundles. The Swift side only ports the part that
depends on live typing: the decoder, fuzzy matching and the English check.

Writes two files (both generated, both git-ignored):

  macos/SingKhmer/Resources/engine_data.json
      index        spelling -> ranked candidates (khmer, score, source)
      khmer_words  every vocabulary word (used to fold repeats into the sign)
      english      the common-English wordlist (code-switching passthrough)

  macos/SingKhmer/Tests/SingKhmerCoreTests/Fixtures/golden.json
      Inputs paired with what THIS Python engine returns for them. The Swift tests
      replay the file, so the port is checked against the real engine rather than
      against a second hand-written copy of the expectations.

Usage (from the project root):
    python3 scripts/export_mac_data.py              # both files
    python3 scripts/export_mac_data.py --data-only  # just the app's data (fast)

Re-run it whenever data/vocabulary.csv changes (macos/SingKhmer/build.sh does this
for you on every build).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sing_khmer_engine.lookup import Engine  # noqa: E402

MAC_DIR = ROOT / "macos" / "SingKhmer"
DATA_PATH = MAC_DIR / "Resources" / "engine_data.json"
GOLDEN_PATH = MAC_DIR / "Tests" / "SingKhmerCoreTests" / "Fixtures" / "golden.json"

FORMAT_VERSION = 1

# Hand-picked inputs covering each behaviour the port has to reproduce.
_HANDWRITTEN = [
    "nh", "jg", "nh srolanh bong", "nhslbong", "bongrean", "bong rean", "msel minh",
    "mselminh", "srolan", "hello bong how are you", "soksabay te", "sok sabay te?",
    "javascript", "computer", "ok bong", "muy muy", "b", "s", "sab", "you",
    "nh  srolanh  bong", "  nh", "nh  ", "Nh Srolanh Bong", "NHSLBONG",
    "nh, bong!", "(bong)", "bong...", "...", "?", "nh jg tov psar", "ot ey te",
    "tver ey", "tv", "map", "do", "xyzzyq", "bong 123", "a", "", " ", "   ",
    "bong's", "'", "nh\tbong", "nh\nbong", "tov na", "mok pi na", "som tos",
    "orkun", "orkun bong", "arkun chraen", "jab", "jong", "ban", "min ban",
]


def build_data(engine: Engine) -> dict:
    """The JSON payload the Mac app loads at startup."""
    return {
        "version": FORMAT_VERSION,
        "index": {
            key: [{"khmer": c.khmer, "score": c.score, "source": c.source} for c in cands]
            for key, cands in engine.index.items()
        },
        "khmer_words": sorted({entry.khmer for entry in engine.vocab}),
        "english": sorted(engine._english),
    }


def _typo(rng: random.Random, word: str) -> str:
    """One random single-character edit (delete, substitute, insert or swap)."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    if not word:
        return rng.choice(letters)
    i = rng.randrange(len(word))
    kind = rng.choice(("delete", "substitute", "insert", "swap"))
    if kind == "delete" and len(word) > 1:
        return word[:i] + word[i + 1:]
    if kind == "substitute":
        return word[:i] + rng.choice(letters) + word[i + 1:]
    if kind == "swap" and i + 1 < len(word):
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    return word[:i] + rng.choice(letters) + word[i:]


def golden_inputs(engine: Engine) -> list[str]:
    """A deterministic spread of inputs: every known spelling, plus sentences,
    run-together text, typos, English mixed in, punctuation and odd spacing."""
    rng = random.Random(20260101)          # fixed seed: same file for the same data
    keys = sorted(engine.index)
    english = sorted(engine._english)
    inputs: list[str] = list(_HANDWRITTEN) + keys

    for _ in range(900):                    # sentences, with and without spaces
        words = [rng.choice(keys) for _ in range(rng.randint(2, 4))]
        inputs.append(rng.choice((" ", " ", "")).join(words))
    for _ in range(700):                    # typos, alone and inside a sentence
        bad = _typo(rng, rng.choice(keys))
        if rng.random() < 0.3:
            bad = _typo(rng, bad)
        inputs.append(bad if rng.random() < 0.6 else f"{rng.choice(keys)} {bad}")
    for _ in range(400):                    # English mixed with Sing Khmer
        words = [rng.choice(english) if rng.random() < 0.5 else rng.choice(keys)
                 for _ in range(rng.randint(1, 4))]
        inputs.append(" ".join(words))
    for _ in range(200):                    # punctuation, capitals, double spaces
        words = [rng.choice(keys) for _ in range(rng.randint(1, 3))]
        words = [w.upper() if rng.random() < 0.2 else w for w in words]
        text = rng.choice((" ", "  ", ", ", "! ", " (")).join(words)
        inputs.append(text + rng.choice(("", "?", "!", ")", "...", "  ")))

    seen: set[str] = set()
    return [t for t in inputs if not (t in seen or seen.add(t))]


def build_golden(engine: Engine) -> dict:
    """What the Python engine returns for each golden input."""
    cases = []
    for text in golden_inputs(engine):
        segments = engine.decode(text)
        cases.append({
            "input": text,
            "text": engine.join_segments(segments),
            "readings": engine.readings(text, k=3),
            "convert": [[c.khmer, c.score, c.source] for c in engine.convert(text)],
            "segments": [
                {
                    "surface": s.surface,
                    "best": s.best,
                    "matched": s.matched,
                    "candidates": [[c.khmer, c.score, c.source] for c in s.candidates],
                }
                for s in segments
            ],
        })
    return {"version": FORMAT_VERSION, "cases": cases}


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-only", action="store_true",
                        help="skip the golden test file (faster; enough to build the app)")
    args = parser.parse_args()

    engine = Engine()
    data = build_data(engine)
    _write(DATA_PATH, data)
    print(f"{len(engine.vocab)} words, {len(data['index'])} spellings, "
          f"{len(data['english'])} English words")
    print(f"  data   -> {DATA_PATH.relative_to(ROOT)} ({DATA_PATH.stat().st_size // 1024} KB)")
    if not args.data_only:
        golden = build_golden(engine)
        _write(GOLDEN_PATH, golden)
        print(f"  golden -> {GOLDEN_PATH.relative_to(ROOT)} ({len(golden['cases'])} cases)")


if __name__ == "__main__":
    main()
