#!/usr/bin/env python3
"""Dump every table to a timestamped JSON file, so the data survives anything.

Neon keeps its own backups and point-in-time restore, but a file you control is the
difference between "probably fine" and "definitely fine".

    DATABASE_URL=... PYTHONPATH=src python scripts/backup_db.py backups/
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import storage  # noqa: E402

TABLES = ("sessions", "conversions", "word_choices", "unknown_words",
          "unknown_word_sessions", "confirmations", "confirmation_sessions", "corrections")


def main() -> int:
    if not storage.available():
        print(f"storage unavailable ({storage.mode()})")
        return 1
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backups")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"sing-khmer-{stamp}.json"

    dump: dict[str, list[dict]] = {}
    with storage.connect() as (conn, _):
        for table in TABLES:
            cur = conn.cursor().execute(f"SELECT * FROM {table}")
            names = [d[0] for d in cur.description]
            dump[table] = [dict(zip(names, r)) for r in cur.fetchall()]

    path.write_text(json.dumps(dump, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    total = sum(len(v) for v in dump.values())
    print(f"wrote {path} ({total} rows across {len(TABLES)} tables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
