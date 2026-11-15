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


def test_multi_word_spelling_is_also_indexed_run_together():
    vocab = [VocabEntry("ម្សិលមិញ", 4, False, ("msel minh",))]
    index = build_index(vocab)
    assert index["msel minh"][0].khmer == "ម្សិលមិញ"
    assert index["mselminh"] == index["msel minh"]


def test_respellings_of_a_real_spelling_are_found_but_rank_below_real_ones():
    from sing_khmer_engine.lookup import Engine
    from sing_khmer_engine.vocabulary import VocabEntry

    def entry(khmer, freq, *roms):
        return VocabEntry(khmer=khmer, frequency=freq, is_slang=False, romanizations=list(roms))

    eng = Engine([entry("ចាប់", 3, "jap"), entry("ខ្លាំង", 3, "klang"),
                  entry("ប្រជុំ", 3, "projum"), entry("ចាប", 1, "jab")], use_english=False)
    assert eng.convert("klg")[0].khmer == "ខ្លាំង"          # klang -> klg
    assert eng.convert("pjum")[0].khmer == "ប្រជុំ"          # projum -> pjum
    assert [c.khmer for c in eng.convert("jab")] == ["ចាប", "ចាប់"]   # real spelling first
    # a short guessed spelling is never used as a piece of a longer run
    assert eng.convert_sentence_text("klgxyz") == "klgxyz"
