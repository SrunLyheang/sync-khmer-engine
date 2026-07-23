"""Tests for the reverse index (step 1.6)."""

from sing_khmer_engine.reverse_index import build_index
from sing_khmer_engine.vocabulary import VocabEntry


def _entry(khmer, roms, freq=5):
    return VocabEntry(khmer=khmer, frequency=freq,
                      is_slang=False, romanizations=tuple(roms))


def test_collected_spelling_maps_to_word():
    idx = build_index([_entry("ទឹក", ["terk"], freq=5)])
    assert [c.khmer for c in idx["terk"]] == ["ទឹក"]
    assert idx["terk"][0].source == "collected"


def test_homophones_ranked_by_frequency():
    vocab = [_entry("ចង់", ["jg"], freq=5), _entry("ចឹង", ["jg"], freq=4)]
    cands = build_index(vocab)["jg"]
    assert [c.khmer for c in cands] == ["ចង់", "ចឹង"]  # higher frequency first


def test_spelling_is_normalized_and_deduped():
    idx = build_index([_entry("ល្អ", ["Loar", "loar", " loar "])])
    assert list(idx) == ["loar"]           # lowercased, stripped, one key
    assert len(idx["loar"]) == 1           # single candidate, not duplicated
