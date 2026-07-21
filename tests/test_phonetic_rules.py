"""Tests for the phonetic-rules builder (step 1.4)."""

from sing_khmer_engine.phonetic_rules import Rule, build_rules, coverage
from sing_khmer_engine.vocabulary import VocabEntry, load


def _entry(khmer, roms, freq=5, slang=False):
    return VocabEntry(khmer=khmer, meaning="", frequency=freq,
                      is_slang=slang, romanizations=tuple(roms))


def test_direct_rule_single_spelling():
    rules = build_rules([_entry("ល្អ", ["loar"])])
    assert rules["ល្អ"] == [Rule("ល្អ", "loar", 1.0, "direct")]


def test_direct_rule_splits_weight_across_spellings():
    rules = build_rules([_entry("ទេ", ["te", "the"])])
    weights = {r.spelling: r.weight for r in rules["ទេ"]}
    assert weights == {"te": 0.5, "the": 0.5}
    assert all(r.source == "direct" for r in rules["ទេ"])


def test_multi_kcc_word_produces_no_exact_rule():
    # ទឹក has two KCCs, so with alignment off no exact rule is derived for its parts.
    rules = build_rules([_entry("ទឹក", ["terk"])])
    assert rules == {}


def test_aligned_is_opt_in_and_anchors_on_known_part():
    vocab = [_entry("ក", ["k"]), _entry("ទឹក", ["terk"])]
    # Off by default: only the single-KCC direct rule exists.
    assert set(build_rules(vocab)) == {"ក"}
    # On: the known suffix "k" anchors, learning ទឹ -> "ter".
    aligned = build_rules(vocab, include_aligned=True)
    assert "ទឹ" in aligned
    assert any(r.spelling == "ter" and r.source == "aligned" for r in aligned["ទឹ"])


def test_weights_sum_to_one_per_kcc_and_no_empty_spellings():
    rules = build_rules(load())
    for kcc, rs in rules.items():
        assert abs(sum(r.weight for r in rs) - 1.0) < 1e-6
        assert all(r.spelling.strip() for r in rs)
        assert all(0 < r.weight <= 1 for r in rs)


def test_coverage_counts():
    vocab = load()
    cov = coverage(vocab, build_rules(vocab))
    assert cov["covered"] + cov["uncovered"] == cov["unique_kccs"]
    assert cov["covered"] > 0
