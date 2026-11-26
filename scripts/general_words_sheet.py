#!/usr/bin/env python3
"""The Khmer-only words (data/wordlist_general.csv) as a sheet to verify spellings in.

Every word gets a row, most frequent first. Spellings come from
data/review/general_spellings.tsv where a word has been checked by hand (checked_by =
claude); otherwise from the romanizer's guesses (checked_by = engine), which are rougher.
Rows flagged `drop` there (fragments, not words) start with keep = n.

    PYTHONPATH=src python scripts/general_words_sheet.py
writes data/review/general_words.csv and .xlsx. Edit keep / khmer / spellings, then merge
what you approved into vocabulary.csv the same way as any review sheet:
    PYTHONPATH=src python scripts/review_words.py merge data/review/general_words.xlsx
(rows you merge become curated words; the rest stay Khmer-only guesses).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sing_khmer_engine.romanizer import Romanizer  # noqa: E402
from sing_khmer_engine.vocabulary import DEFAULT_GENERAL_PATH, load  # noqa: E402

HAND = ROOT / "data" / "review" / "general_spellings.tsv"
OUT = ROOT / "data" / "review" / "general_words.csv"
COLUMNS = ["keep", "khmer", "spellings", "english", "checked_by", "engine_guess", "rank",
           "category", "register", "source"]


def read_hand(path: Path) -> dict[str, tuple[str, str, str]]:
    out: dict[str, tuple[str, str, str]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = (line.split("\t") + ["", "", ""])[:4]
        out[parts[0].strip()] = (parts[1].strip(), parts[2].strip(), parts[3].strip())
    return out


def main() -> None:
    rom = Romanizer(load())
    hand = read_hand(HAND)
    rows = []
    with DEFAULT_GENERAL_PATH.open(encoding="utf-8") as f:
        for rank, r in enumerate(csv.DictReader(f), start=1):
            khmer = r["khmer"]
            guesses = [rom.romanize(khmer)] + [v for v in rom.variants(khmer) if v != rom.romanize(khmer)]
            spellings, english, flag = hand.get(khmer, ("", "", ""))
            checked = khmer in hand
            rows.append({
                "keep": "n" if flag == "drop" else "y",
                "khmer": khmer,
                "spellings": spellings if checked else ", ".join(guesses[:2]),
                "english": english,
                "checked_by": "claude" if checked else "engine",
                "engine_guess": ", ".join(guesses[:3]),
                "rank": rank,
                "category": "general",
                "register": "",
                "source": r.get("source", ""),
            })
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    write_xlsx(OUT.with_suffix(".xlsx"), rows)
    done = sum(r["checked_by"] == "claude" for r in rows)
    print(f"{len(rows)} words: {done} hand-checked, {len(rows) - done} engine guesses "
          f"-> {OUT.relative_to(ROOT)} and .xlsx")


def write_xlsx(path: Path, rows: list[dict]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "verify"
    ws.append(COLUMNS)
    engine_fill = PatternFill("solid", fgColor="F2F2F2")
    for i, r in enumerate(rows, start=2):
        ws.append([r[c] for c in COLUMNS])
        if r["checked_by"] == "engine":
            for cell in ws[i]:
                cell.fill = engine_fill          # grey = rough guess, not checked yet
    editable = PatternFill("solid", fgColor="FFF4CC")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        if cell.value in ("keep", "khmer", "spellings"):
            cell.fill = editable
    widths = [6, 18, 30, 30, 11, 30, 7, 9, 9, 18]
    for i, wdt in enumerate(widths):
        ws.column_dimensions[chr(ord("A") + i)].width = wdt
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    dv = DataValidation(type="list", formula1='"y,n"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"A2:A{len(rows) + 1}")
    wb.save(path)


if __name__ == "__main__":
    main()
