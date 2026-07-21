"""Tests for Khmer Character Cluster segmentation (step 1.3)."""

import pytest

from sing_khmer_engine.kcc import segment

# (input, expected clusters)
CASES = [
    ("ចឹង", ["ចឹ", "ង"]),
    ("ស្អាត", ["ស្អា", "ត"]),
    ("ខ្ញុំ", ["ខ្ញុំ"]),
    ("សួស្តី", ["សួ", "ស្តី"]),
    ("អរគុណ", ["អ", "រ", "គុ", "ណ"]),
    ("ទឹក", ["ទឹ", "ក"]),
    ("មក", ["ម", "ក"]),  # no combining marks: one cluster per base
]


@pytest.mark.parametrize("word,expected", CASES)
def test_segment_known_words(word, expected):
    assert segment(word) == expected


@pytest.mark.parametrize("word,expected", CASES)
def test_segments_rejoin_to_original(word, expected):
    """Segmentation is lossless: joining the clusters rebuilds the input."""
    assert "".join(segment(word)) == word


def test_empty_string():
    assert segment("") == []


def test_mixed_latin_and_space():
    # Non-Khmer characters each become their own token.
    assert segment("ok ណា") == ["o", "k", " ", "ណា"]


def test_lossless_on_mixed():
    s = "ខ្ញុំ love ចឹង"
    assert "".join(segment(s)) == s
