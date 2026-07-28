#!/usr/bin/env python3
"""Print what users have sent, straight from whatever database is configured.

This is the quick answer to "someone submitted a missing word — where did it go?".
`/admin` needs ADMIN_TOKEN set and `export_feedback.py` builds an Excel file; this needs
neither. It only reads.

    python scripts/show_feedback.py            # everything, most recent first
    python scripts/show_feedback.py 100        # show more rows per section

It prints the resolved database location first, so an empty result tells you *which* empty
database you are looking at — the usual surprise is a local run reading a different file
than the deployment.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from api import storage  # noqa: E402


def table(title: str, note: str, headers: list[str], rows: list[list]) -> None:
    print(f"\n{title}")
    print(f"  {note}")
    if not rows:
        print("  (nothing yet)")
        return
    cells = [headers] + [[str(c) for c in r] for r in rows]
    # Khmer renders wider than len() suggests; pad by codepoints and accept slight drift
    # rather than pulling in a wcwidth dependency for a debug script.
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers))]
    for i, row in enumerate(cells):
        print("  " + "  ".join(c.ljust(w) for c, w in zip(row, widths)))
        if i == 0:
            print("  " + "  ".join("-" * w for w in widths))


def main(limit: int = 50) -> int:
    print(f"database: {storage.location()}")
    if not storage.available():
        print("\nStorage is disabled, so nothing is being recorded at all.")
        return 1

    storage.migrate()
    with storage.connect() as (conn, _):
        cur = conn.cursor()

        table(
            'Words people sent through "Missing a word?"',
            "grouped by answer — `people` is how many different visitors said the same thing",
            ["they typed", "should be", "people", "times", "where", "last sent"],
            [
                [c["spelling"], c["khmer"], c["people"], c["times"], c["source"], c["last_seen"]]
                for c in storage.recent_corrections(cur, limit)
            ],
        )

        cur.execute(
            "SELECT spelling, total_count, session_count FROM unknown_words"
            f" ORDER BY session_count DESC, total_count DESC LIMIT {int(limit)}"
        )
        table(
            "Words the engine couldn't convert",
            "nobody told us what these should be — the coverage gap",
            ["spelling", "times", "people"],
            [list(r) for r in cur.fetchall()],
        )

        cur.execute(
            "SELECT spelling, engine_top, chosen, COUNT(DISTINCT session_id), COUNT(*)"
            " FROM word_choices GROUP BY spelling, engine_top, chosen"
            f" ORDER BY 4 DESC, 5 DESC LIMIT {int(limit)}"
        )
        table(
            "Words people corrected by tapping a different option",
            "strongest evidence you have: they picked it and then used it",
            ["spelling", "engine said", "they chose", "people", "times"],
            [list(r) for r in cur.fetchall()],
        )

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 50))
