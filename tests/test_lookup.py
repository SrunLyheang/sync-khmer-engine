"""Tests for the core lookup engine (step 1.7)."""

from sing_khmer_engine.lookup import Engine, lookup
from sing_khmer_engine.vocabulary import VocabEntry


def _engine(entries):
    return Engine(entries, use_generated=False)


def test_exact_match_returns_word():
    eng = _engine([VocabEntry("ខ្ញុំ", "", 5, False, ("nh", "knh"))])
    assert [c.khmer for c in eng.convert("nh")] == ["ខ្ញុំ"]


def test_input_is_case_and_space_insensitive():
    eng = _engine([VocabEntry("ខ្ញុំ", "", 5, False, ("nh",))])
    assert eng.convert("  NH ")[0].khmer == "ខ្ញុំ"


def test_unknown_input_returns_empty():
    eng = _engine([VocabEntry("ខ្ញុំ", "", 5, False, ("nh",))])
    assert eng.convert("zzz") == []


def test_limit_is_respected():
    vocab = [VocabEntry(k, "", 5, False, ("x",)) for k in ("ក", "ខ", "គ", "ឃ")]
    assert len(_engine(vocab).convert("x", limit=2)) == 2


def test_real_data_homophone_ranking():
    """On the real vocabulary, `jg` yields ចង់ (freq 5) before ចឹង (freq 4)."""
    eng = Engine()  # loads data/vocabulary.csv
    names = [c.khmer for c in eng.convert("jg")]
    assert "ចង់" in names and "ចឹង" in names
    assert names.index("ចង់") < names.index("ចឹង")
    assert lookup("nh", engine=eng)[0].khmer == "ខ្ញុំ"


def test_sentence_conversion_joins_words():
    eng = Engine()
    assert eng.convert_sentence_text("nh sl bong") == "ខ្ញុំ ស្រឡាញ់ បង"


def test_decoder_handles_no_spaces():
    """The segmentation decoder converts run-together input with no spaces."""
    eng = Engine()
    assert eng.convert_sentence_text("nhslbong") == "ខ្ញុំ ស្រឡាញ់ បង"


def test_decoder_matches_multiword_spelling():
    """A multi-word spelling (space inside one spelling) matches as one unit."""
    eng = Engine()
    assert eng.convert_sentence_text("msel minh") == "ម្សិលមិញ"


def test_decoder_passes_unknown_words_through():
    eng = Engine()
    segs = eng.convert_sentence("nh zzzzq bong")
    bests = [s.best for s in segs]
    assert "ខ្ញុំ" in bests and "បង" in bests
    assert any(s.surface == "zzzzq" and not s.matched for s in segs)
