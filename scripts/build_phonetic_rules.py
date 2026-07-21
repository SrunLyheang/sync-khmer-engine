#!/usr/bin/env python3
"""Build the phonetic-rules table from the vocabulary and save it (step 1.4).

Writes:
  data/phonetic_rules.csv         — exact KCC -> spelling rules (kcc,spelling,weight,source)
  data/phonetic_rules_review.csv  — KCCs with no exact rule yet, with example words as context

Usage (from the project root):
    PYTHONPATH=src python scripts/build_phonetic_rules.py
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sing_khmer_engine.kcc import segment          # noqa: E402
from sing_khmer_engine.phonetic_rules import build_rules, coverage  # noqa: E402
from sing_khmer_engine.vocabulary import load       # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    vocab = load()
    rules = build_rules(vocab)  # exact (direct) rules only
    cov = coverage(vocab, rules)

    # 1) rules table
    rules_path = DATA / "phonetic_rules.csv"
    with rules_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kcc", "spelling", "weight", "source"])
        for kcc in sorted(rules):
            for r in rules[kcc]:
                w.writerow([r.kcc, r.spelling, r.weight, r.source])

    # 2) review file: uncovered KCCs + example words for the native speaker
    examples: dict[str, list[str]] = defaultdict(list)
    for e in vocab:
        for k in segment(e.khmer):
            if k not in rules and len(examples[k]) < 3:
                examples[k].append(f"{e.khmer} ({' '.join(e.romanizations)})")
    review_path = DATA / "phonetic_rules_review.csv"
    with review_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kcc", "spelling", "example_words"])
        for kcc in sorted(examples):
            w.writerow([kcc, "", " | ".join(examples[kcc])])

    print(f"coverage: {cov['covered']}/{cov['unique_kccs']} unique KCCs have exact rules "
          f"({cov['uncovered']} still need spellings)")
    print(f"wrote {rules_path.name} and {review_path.name}")
    print("\nsample exact rules:")
    for kcc in list(sorted(rules))[:12]:
        print(f"  {kcc:6} -> " + ", ".join(f"{r.spelling}({r.weight})" for r in rules[kcc]))


if __name__ == "__main__":
    main()
