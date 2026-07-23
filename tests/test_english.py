"""Tests for common-English detection (Phase 3)."""

from sing_khmer_engine.english import is_english, load_english


def test_bundled_list_loads_common_words():
    words = load_english()
    assert "computer" in words and "javascript" in words and "message" in words


def test_short_sing_khmer_abbreviations_are_not_english():
    """nh / sl / jg are Sing Khmer, not English — they must be filtered out."""
    words = load_english()
    for abbr in ("nh", "sl", "jg"):
        assert abbr not in words


def test_is_english_is_case_insensitive():
    words = load_english()
    assert is_english("Computer", words)
    assert is_english("  OK ", words)
    assert not is_english("zzzzq", words)


def test_missing_file_disables_detection():
    assert load_english("/no/such/file.txt") == frozenset()
