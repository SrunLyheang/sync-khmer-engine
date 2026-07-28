#!/usr/bin/env python3
"""Turn real usage into reviewable vocabulary — ranked by how much the evidence proves.

There is no ground truth for informal romanization, so nothing here is ever written into
`data/vocabulary.csv` automatically. Instead this ranks what users did by how convincing it
is, so review time goes to the strongest evidence first:

  Sheet 1  Engine ranked wrong  — someone picked a different candidate and then USED it.
                                  Strongest: they acted on it, they didn't just claim it.
  Sheet 2  Corrections          — someone told us the Khmer for a spelling. Ranked by how
                                  many DIFFERENT people gave the same answer (agreement).
  Sheet 3  Missing words        — spellings the engine couldn't convert, ranked by how many
                                  different people hit them. This is your coverage gap.

Every row carries a "people" count: one person could be wrong or joking; five independent
people agreeing is about as close to truth as this problem allows.

    DATABASE_URL=... PYTHONPATH=src python scripts/export_feedback.py [out.xlsx] [limit]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from api import storage  # noqa: E402


def collect(limit: int) -> dict[str, list[tuple]]:
    """The same three views /admin downloads — the queries live in storage.EXPORTS so this
    spreadsheet and that download can't drift into disagreeing about the data."""
    return {name: storage.export_data(name, limit)[1] for name in storage.EXPORTS}


def write_xlsx(path: Path, data: dict[str, list[tuple]]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    fill = PatternFill("solid", fgColor="0F766E")
    hfont = Font(color="FFFFFF", bold=True, size=12)
    thin = Side(style="thin", color="CCCCCC")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    khmer, mono = Font(name="Khmer OS", size=16), Font(name="Consolas", size=12)

    def sheet(ws, note, headers, widths, rows, kinds):
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws.cell(row=1, column=1, value=note).font = Font(italic=True, color="555555", size=11)
        ws.cell(row=1, column=1).alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[1].height = 42
        for c, h in enumerate(headers, 1):
            x = ws.cell(row=2, column=c, value=h)
            x.fill, x.font, x.border = fill, hfont, box
            x.alignment = Alignment(horizontal="center", vertical="center")
        for i, row in enumerate(rows, 1):
            for c, (value, kind) in enumerate(zip(row, kinds), 1):
                cell = ws.cell(row=i + 2, column=c, value=value)
                if kind == "km":
                    cell.font = khmer
                elif kind == "mono":
                    cell.font = mono
                cell.border = box
        ws.freeze_panes = "A3"
        for col, w in zip("ABCDEFG", widths):
            ws.column_dimensions[col].width = w

    ws = wb.active
    ws.title = "1 Engine ranked wrong"
    sheet(
        ws,
        "STRONGEST evidence: the person picked a different word and then used it. 'used' = they "
        "copied it afterwards. If you agree, raise that spelling's ranking (or add the mapping).",
        ["they typed", "engine put first", "they chose", "people", "times", "used", "✅ / note"],
        [18, 18, 18, 8, 8, 8, 22],
        [(s, e, c, p, t, u, "") for s, e, c, p, t, u in data["overrides"]],
        ["mono", "km", "km", "n", "n", "n", ""],
    )

    sheet(
        wb.create_sheet("2 Corrections"),
        "People told us what a spelling should be. 'people' is how many DIFFERENT people gave "
        "this same answer — 1 person could be wrong or joking; several agreeing is strong.",
        ["they typed", "they say it means", "people", "times", "how", "✅ / fix"],
        [18, 20, 8, 8, 10, 22],
        [(s, k, p, t, src, "") for s, k, p, t, src in data["corrections"]],
        ["mono", "km", "n", "n", "", ""],
    )

    sheet(
        wb.create_sheet("3 Missing words"),
        "Spellings the engine could not convert at all — your coverage gap, ranked by how many "
        "different people hit them. Fill in the Khmer and these become new dictionary entries.",
        ["they typed", "people", "times", "Khmer it should be", "note"],
        [18, 8, 8, 22, 20],
        [(s, p, t, "", "") for s, p, t in data["missing"]],
        ["mono", "n", "n", "km", ""],
    )
    wb.save(path)


def main() -> int:
    if not storage.available():
        print(f"storage unavailable ({storage.mode()}) — set DATABASE_URL")
        return 1
    storage.migrate()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "user_feedback.xlsx"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    data = collect(limit)
    print(f"source: {storage.mode()}")
    print(f"  engine ranked wrong : {len(data['overrides'])}")
    print(f"  corrections sent    : {len(data['corrections'])}")
    print(f"  missing words       : {len(data['missing'])}")
    if not any(data.values()):
        print("nothing collected yet — share the app and come back later.")
        return 0
    write_xlsx(out, data)
    print(f"wrote {out}")
    print("review it, then fold the rows you agree with into data/vocabulary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
