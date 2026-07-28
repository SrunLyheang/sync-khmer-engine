#!/usr/bin/env python3
"""Delete raw message text once it's older than the retention window.

Only `conversions.input_text` / `output_text` hold what people actually wrote. Every useful
signal (missing words, corrections, which candidate people picked) was derived at write time
into tables that never expire — so deleting old messages costs nothing analytically and is a
real privacy win.

Run it on a schedule (cron, or a Vercel Cron hitting a small wrapper):

    DATABASE_URL=... PYTHONPATH=src python scripts/purge.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import storage  # noqa: E402


def main() -> int:
    if not storage.available():
        print(f"storage unavailable ({storage.mode()}) — nothing to do")
        return 1
    deleted = storage.purge_expired()
    print(f"deleted {deleted} message(s) older than {storage.RAW_TEXT_TTL_DAYS} days")
    print("derived signals (missing words, corrections, choices) were left untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
