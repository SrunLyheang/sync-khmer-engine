"""Tests for common-English detection (Phase 3)."""

from sing_khmer_engine.english import is_english, load_english


def test_bundled_list_loads_common_words():
    words = load_english()
    assert "computer" in words and "javascript" in words and "message" in words


def test_list_noise_that_looks_like_sing_khmer_is_filtered():
    """Short entries are kept only if genuinely common, so google-list noise that is really
    Sing Khmer (dg=ដឹង, der=ដើរ, das=ដាស់, av=អាវ) never counts as English."""
    words = load_english()
    for noise in ("dg", "der", "das", "av", "nh", "sl", "jg"):
        assert noise not in words
    for real in ("do", "no", "map", "tv"):     # ...while real short words survive
        assert real in words


def test_is_english_is_case_insensitive():
    words = load_english()
    assert is_english("Computer", words)
    assert is_english("  OK ", words)
    assert not is_english("zzzzq", words)


def test_missing_file_disables_detection():
    assert load_english("/no/such/file.txt") == frozenset()
