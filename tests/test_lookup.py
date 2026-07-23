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


def test_sentence_conversion_runs_khmer_together():
    """Khmer output has NO spaces between words (as Khmer is actually written)."""
    eng = Engine()
    assert eng.convert_sentence_text("nh sl bong") == "ខ្ញុំស្រឡាញ់បង"


def test_decoder_handles_no_spaces():
    """The segmentation decoder converts run-together input with no spaces."""
    eng = Engine()
    assert eng.convert_sentence_text("nhslbong") == "ខ្ញុំស្រឡាញ់បង"


def test_decoder_matches_multiword_spelling():
    """A multi-word spelling (space inside one spelling) matches as one unit."""
    eng = Engine()
    assert eng.convert_sentence_text("msel minh") == "ម្សិលមិញ"


def test_compound_word_preferred_over_split():
    """A whole compound word beats splitting it into two known words."""
    eng = Engine()
    assert eng.convert_sentence_text("bongrean") == "បង្រៀន"  # not បង រៀន


def test_readings_offers_compound_and_split():
    """Alternative readings let the user switch compound <-> split."""
    eng = Engine()
    r = eng.readings("bongrean")
    assert "បង្រៀន" in r and "បងរៀន" in r   # compound vs. split (both no-space)
    assert r[0] == "បង្រៀន"  # compound first


def test_decoder_passes_unknown_words_through():
    eng = Engine()
    segs = eng.convert_sentence("nh zzzzq bong")
    bests = [s.best for s in segs]
    assert "ខ្ញុំ" in bests and "បង" in bests
    assert any(s.surface == "zzzzq" and not s.matched for s in segs)


def test_double_space_commits_a_real_space():
    """A single space is a word boundary (no space in Khmer); a double space
    commits a real space between the two words."""
    eng = Engine()
    assert eng.convert_sentence_text("nh sl") == "ខ្ញុំស្រឡាញ់"       # single = joined
    assert eng.convert_sentence_text("nh  sl") == "ខ្ញុំ ស្រឡាញ់"    # double = real space


def test_repeated_word_folds_to_repetition_sign():
    """Typing a word twice renders the second as ៗ (មួយ + ៗ), with the doubled
    form (មួយមួយ) offered as an alternative reading."""
    eng = Engine()
    assert eng.convert_sentence_text("muy muy") == "មួយៗ"
    assert "មួយមួយ" in eng.readings("muy muy")


def test_double_space_prevents_repetition_fold():
    """A deliberate real space (double space) keeps the two words separate — no ៗ."""
    eng = Engine()
    assert eng.convert_sentence_text("muy  muy") == "មួយ មួយ"


def test_unknown_word_passes_through_instead_of_gibberish():
    """A word the engine can only match by chopping into junk is left as Latin,
    not turned into gibberish Khmer."""
    eng = Engine()
    for word in ("javascript", "helloworld", "programming"):
        segs = eng.decode(word)
        assert len(segs) == 1
        assert not segs[0].matched          # passed through
        assert segs[0].surface == word


def test_confidence_gate_keeps_real_no_space_khmer():
    """The gate must NOT fire on legitimate run-together Sing Khmer (0 unmatched)."""
    eng = Engine()
    assert eng.convert_sentence_text("nhslbong") == "ខ្ញុំស្រឡាញ់បង"


def test_unknown_word_passes_through_in_a_sentence():
    """An unknown word between known ones passes through; the rest still converts."""
    eng = Engine()
    segs = eng.decode("nh javascript sl")
    assert any(s.surface == "javascript" and not s.matched for s in segs)
    bests = [s.best for s in segs]
    assert "ខ្ញុំ" in bests and "ស្រឡាញ់" in bests
