"""Tests for edit-distance fuzzy matching (step 1.8)."""

from sing_khmer_engine.fuzzy import levenshtein, within
from sing_khmer_engine.lookup import Engine


def test_levenshtein_basic():
    assert levenshtein("srolan", "srolanh") == 1
    assert levenshtein("abc", "abc") == 0
    assert levenshtein("", "abc") == 3
    assert levenshtein("kitten", "sitting") == 3


def test_within_prunes_and_bounds():
    assert within("srolan", "srolanh", 2) == 1
    assert within("abc", "abcdef", 2) is None   # length gap > k, pruned
    assert within("cat", "dog", 1) is None       # too far


def test_fuzzy_recovers_from_typo():
    eng = Engine()
    res = eng.convert("srolan")                  # missing the trailing 'h'
    assert res and res[0].khmer == "ស្រឡាញ់"
    assert res[0].source == "fuzzy"


def test_exact_still_beats_fuzzy_and_is_labeled():
    eng = Engine()
    res = eng.convert("srolanh")
    assert res[0].khmer == "ស្រឡាញ់"
    assert res[0].source != "fuzzy"              # exact hit, not a fuzzy fallback


def test_fuzzy_can_be_disabled():
    eng = Engine()
    assert eng.convert("srolan", fuzzy=False) == []


def test_gibberish_has_no_match():
    assert Engine().convert("zzzzq") == []
