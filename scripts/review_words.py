#!/usr/bin/env python3
"""Turn a researched word list into a review sheet, then merge what you approved.

Step 1 — build the sheet you review:
    PYTHONPATH=src python scripts/review_words.py build data/review/movie_words_source.tsv
  writes data/review/movie_words.csv and .xlsx (same rows; edit whichever you like).

  Columns you edit:
    keep        leave as "y"; change to "n" to drop the row
    spellings   the Sing Khmer you actually type, comma-separated; "+" joins the words of
                one multi-word spelling (kom+tov). Fix my guesses here.
    khmer       fix the Khmer if I got the word itself wrong
  Columns for reference only: engine_guess (what the romanizer predicts), english, chinese,
  category, register, status (new / adds spellings / already covered).

Optional — a short sheet of the words that matter most:
    PYTHONPATH=src python scripts/review_words.py top data/review/movie_words.csv SEAFREQ
  writes movie_words_top100.csv/.xlsx: the 100 rows used most in general Khmer (frequency
  list rank), then dialogue and pronouns first. Review these spellings carefully; the rest
  can stay Khmer-only guesses (data/wordlist_general.csv) and be taught while typing.

Step 2 — merge your reviewed sheet into data/vocabulary.csv:
    PYTHONPATH=src python scripts/review_words.py merge data/review/movie_words.xlsx
  (or the .csv). Add --dry-run to preview. Existing words only gain spellings; nothing is
  removed. New rows get frequency 3 and a note with the English / Chinese meaning.

The source file is tab-separated: khmer, spellings, english, chinese, category, register.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from import_mac_words import merge  # noqa: E402
from sing_khmer_engine.romanizer import Romanizer  # noqa: E402
from sing_khmer_engine.vocabulary import DEFAULT_VOCAB_PATH, load, parse_romanizations  # noqa: E402

COLUMNS = ["keep", "khmer", "spellings", "engine_guess", "english", "chinese",
           "category", "register", "status"]


def read_source(path: Path) -> list[dict]:
    rows, seen = [], set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = (line.split("\t") + [""] * 6)[:6]
        khmer = parts[0].strip()
        if not khmer or khmer in seen:
            continue
        seen.add(khmer)
        rows.append(dict(zip(["khmer", "spellings", "english", "chinese", "category",
                              "register"], (p.strip() for p in parts))))
    return rows


def build(source: Path) -> None:
    vocab = load()
    by_khmer = {e.khmer: e for e in vocab}
    rom = Romanizer(vocab)
    out_rows = []
    covered: list[str] = []
    source = source.resolve()
    for row in read_source(source):
        mine = list(parse_romanizations(row["spellings"]))
        existing = by_khmer.get(row["khmer"])
        if existing is None:
            status = "new"
        else:
            extra = [s for s in mine if s not in existing.romanizations]
            if not extra:                 # nothing to review: the dictionary has it all
                covered.append(row["khmer"])
                continue
            status = f"in dictionary; adds {', '.join(extra)}"
        out_rows.append({
            "keep": "y", **row,
            "engine_guess": rom.romanize(row["khmer"]),
            "status": status,
        })
    stem = source.with_name(source.name.replace("_source.tsv", "")).with_suffix("")
    csv_path, xlsx_path = stem.with_suffix(".csv"), stem.with_suffix(".xlsx")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)
    _write_xlsx(xlsx_path, out_rows)
    counts: dict[str, int] = {}
    for r in out_rows:
        key = r["status"].split(";")[0]
        counts[key] = counts.get(key, 0) + 1
    print(f"{len(out_rows)} rows -> {csv_path} and {xlsx_path}")
    if covered:
        print(f"  {len(covered):4}  skipped (already in the dictionary with these spellings)")
    for k, v in counts.items():
        print(f"  {v:4}  {k}")


def _write_xlsx(path: Path, rows: list[dict]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "review"
    ws.append(COLUMNS)
    for r in rows:
        ws.append([r[c] for c in COLUMNS])
    bold = Font(bold=True)
    editable = PatternFill("solid", fgColor="FFF4CC")
    for cell in ws[1]:
        cell.font = bold
        if cell.value in ("keep", "khmer", "spellings"):
            cell.fill = editable
    widths = {"keep": 6, "khmer": 18, "spellings": 28, "engine_guess": 18, "english": 34,
              "chinese": 16, "category": 11, "register": 9, "status": 34}
    for i, c in enumerate(COLUMNS):
        ws.column_dimensions[chr(ord("A") + i)].width = widths[c]
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    dv = DataValidation(type="list", formula1='"y,n"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"A2:A{len(rows) + 1}")
    wb.save(path)


def read_reviewed(path: Path) -> list[dict]:
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        ws = load_workbook(path, read_only=True).active
        it = ws.iter_rows(values_only=True)
        header = [str(h or "").strip() for h in next(it)]
        return [{h: ("" if v is None else str(v)).strip() for h, v in zip(header, r)}
                for r in it]
    with path.open(encoding="utf-8") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def merge_reviewed(path: Path, dry_run: bool) -> None:
    pairs: list[tuple[str, str]] = []
    notes: dict[str, str] = {}
    for r in read_reviewed(path):
        if not r.get("khmer") or r.get("keep", "y").lower().startswith("n"):
            continue
        meaning = " / ".join(x for x in (r.get("english"), r.get("chinese")) if x)
        tag = ", ".join(x for x in (r.get("category"), r.get("register")) if x)
        notes[r["khmer"]] = f"{meaning} ({tag}; reviewed)".strip()
        for spelling in parse_romanizations(r.get("spellings", "")):
            pairs.append((spelling, r["khmer"]))
    original = DEFAULT_VOCAB_PATH.read_text(encoding="utf-8")
    updated, summary = merge(original, pairs, note=notes)
    print("\n".join(summary) or "Nothing to change.")
    if dry_run or not summary:
        print(f"\n(dry run) {len(summary)} change(s) not written." if dry_run else "")
        return
    DEFAULT_VOCAB_PATH.write_text(updated, encoding="utf-8")
    load()                                        # fail loudly if the file is no longer valid
    print(f"\n{len(summary)} change(s) written. Review with: git diff data/vocabulary.csv")


# Kinds of words a translator types most in dialogue, for ranking words the frequency
# list does not rank (it is built from written text, not speech).
_CATEGORY_ORDER = ["pronoun", "dialogue", "emotion", "romance", "family", "verb", "insult",
                   "time", "crime", "action", "office", "hospital", "fantasy", "modern",
                   "place", "school", "meta"]


def top(sheet: Path, seafreq: Path, count: int) -> None:
    rank: dict[str, int] = {}
    for i, line in enumerate(seafreq.read_text(encoding="utf-8").splitlines()):
        word = line.split("\t")[0].strip()
        rank.setdefault(word, i)
    rows = read_reviewed(sheet)

    def key(r: dict) -> tuple:
        cat = r.get("category", "")
        order = _CATEGORY_ORDER.index(cat) if cat in _CATEGORY_ORDER else len(_CATEGORY_ORDER)
        return (rank.get(r["khmer"], 10**9), order)

    chosen = sorted(rows, key=key)[:count]
    stem = sheet.with_suffix("")
    out_csv = stem.with_name(f"{stem.name}_top{count}.csv")
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in COLUMNS} for r in chosen)
    _write_xlsx(out_csv.with_suffix(".xlsx"), [{c: r.get(c, "") for c in COLUMNS} for r in chosen])
    ranked = sum(r["khmer"] in rank for r in chosen)
    print(f"{len(chosen)} rows ({ranked} ranked by the frequency list, the rest by category) "
          f"-> {out_csv} and .xlsx")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="make the review sheet from a researched .tsv")
    b.add_argument("source", type=Path)
    m = sub.add_parser("merge", help="merge a reviewed .xlsx/.csv into vocabulary.csv")
    m.add_argument("sheet", type=Path)
    m.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("top", help="the most-used rows of a sheet, to review first")
    t.add_argument("sheet", type=Path)
    t.add_argument("seafreq", type=Path)
    t.add_argument("--count", type=int, default=100)
    a = p.parse_args()
    if a.cmd == "build":
        build(a.source)
    elif a.cmd == "top":
        top(a.sheet, a.seafreq, a.count)
    else:
        merge_reviewed(a.sheet, a.dry_run)


if __name__ == "__main__":
    main()
