"""The researched-word review sheet (scripts/review_words.py): build, then merge what was kept."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_spec = importlib.util.spec_from_file_location("review_words", _SCRIPTS / "review_words.py")
review_words = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review_words)

_VOCAB = (
    "khmer,frequency,is_slang,romanizations,notes\n"
    'បង,5,false,"bong, b",keep me\n'
)


def _sheet(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "reviewed.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=review_words.COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in review_words.COLUMNS})
    return path


def test_merge_keeps_only_approved_rows_and_notes_the_meaning(tmp_path, monkeypatch):
    vocab = tmp_path / "vocabulary.csv"
    vocab.write_text(_VOCAB, encoding="utf-8")
    monkeypatch.setattr(review_words, "DEFAULT_VOCAB_PATH", vocab)
    monkeypatch.setattr(review_words, "load", lambda: None)
    sheet = _sheet(tmp_path, [
        {"keep": "y", "khmer": "កុំទៅ", "spellings": "kom+tov, komtov",
         "english": "don't go", "chinese": "别走", "category": "dialogue", "register": "neutral"},
        {"keep": "n", "khmer": "ខុស", "spellings": "khos"},
        {"keep": "y", "khmer": "បង", "spellings": "bong, bg"},
    ])
    review_words.merge_reviewed(sheet, dry_run=False)
    rows = {r["khmer"]: r for r in csv.DictReader(vocab.open(encoding="utf-8"))}
    assert rows["កុំទៅ"]["romanizations"] == "kom+tov, komtov"
    assert rows["កុំទៅ"]["notes"] == "don't go / 别走 (dialogue, neutral; reviewed)"
    assert "ខុស" not in rows                                   # keep = n
    assert rows["បង"]["romanizations"] == "bong, b, bg"         # existing word gains a spelling
    assert rows["បង"]["notes"] == "keep me"                    # and is otherwise untouched


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    vocab = tmp_path / "vocabulary.csv"
    vocab.write_text(_VOCAB, encoding="utf-8")
    monkeypatch.setattr(review_words, "DEFAULT_VOCAB_PATH", vocab)
    sheet = _sheet(tmp_path, [{"keep": "y", "khmer": "កុំទៅ", "spellings": "kom+tov"}])
    review_words.merge_reviewed(sheet, dry_run=True)
    assert vocab.read_text(encoding="utf-8") == _VOCAB
