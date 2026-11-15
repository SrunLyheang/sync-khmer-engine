"""Merging the Mac keyboard's my_words.txt into the vocabulary (scripts/import_mac_words.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sing_khmer_engine.vocabulary import DEFAULT_VOCAB_PATH

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_mac_words.py"
_spec = importlib.util.spec_from_file_location("import_mac_words", _SCRIPT)
import_mac_words = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(import_mac_words)

_CSV = (
    "khmer,frequency,is_slang,romanizations,notes\n"
    'បង,5,false,"bong, b",keep me\n'
    "ម្សិលមិញ,4,false,msel+minh,\n"
)


def test_parse_words_matches_the_swift_rules():
    text = "# comment\njrern  ច្រើន\nOt Ey = អត់អី\n\nno khmer here\n១២៣\njrern ច្រើន\n"
    assert import_mac_words.parse_words(text) == [("jrern", "ច្រើន"), ("ot ey", "អត់អី")]


def test_merge_adds_spellings_and_new_words_without_touching_the_rest():
    words = [("bong", "បង"), ("bng", "បង"), ("ot ey", "អត់អី"), ("msel minh", "ម្សិលមិញ")]
    updated, summary = import_mac_words.merge(_CSV, words)

    assert updated.splitlines() == [
        "khmer,frequency,is_slang,romanizations,notes",
        'បង,5,false,"bong, b, bng",keep me',
        "ម្សិលមិញ,4,false,msel+minh,",
        "អត់អី,3,false,ot+ey,(from Mac keyboard)",
    ]
    assert len(summary) == 2
    assert import_mac_words.merge(updated, words) == (updated, [])   # running twice is harmless


def test_merge_leaves_the_real_vocabulary_byte_identical_when_nothing_is_new():
    original = DEFAULT_VOCAB_PATH.read_text(encoding="utf-8")
    assert import_mac_words.merge(original, []) == (original, [])
