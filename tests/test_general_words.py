"""Khmer-only words (data/wordlist_general.csv) and the learned guessing edits."""

from __future__ import annotations

from sing_khmer_engine.lookup import Engine
from sing_khmer_engine.romanizer import Romanizer
from sing_khmer_engine.vocabulary import VocabEntry, load, load_general


def test_general_words_load_without_spellings_and_skip_curated(tmp_path):
    path = tmp_path / "general.csv"
    path.write_text("khmer,frequency,source\nកុំទៅ,2,x\nបង,3,x\nកុំទៅ,1,x\n", encoding="utf-8")
    words = load_general(path, exclude={"បង"})
    assert [(w.khmer, w.frequency, w.romanizations) for w in words] == [("កុំទៅ", 2, ())]
    assert load_general(tmp_path / "missing.csv") == []


def test_general_words_rank_below_curated_and_only_through_guesses():
    vocab = [VocabEntry("បង", 5, False, ("bong",))]
    eng = Engine(vocab, general=[VocabEntry("បុង", 3, False)])
    assert eng.convert("bong")[0].khmer == "បង"
    sources = {c.source for key, cands in eng.index.items() for c in cands if c.khmer == "បុង"}
    assert sources == {"generated"}


def test_a_guessed_spelling_never_turns_english_into_khmer():
    eng = Engine(load(), general=[VocabEntry("អុក", 3, False)])
    assert any(c.khmer == "អុក" for c in eng.index.get("ok", []))   # it is a guess for អុក
    assert eng.convert_sentence_text("ok") == "ok"                  # but "ok" stays English


def test_edits_are_learned_from_real_spellings():
    rom = Romanizer(load())
    assert rom.edits, "the curated spellings teach at least some edits"
    assert all(n >= 2 for _a, _b, n in rom.edits)
    guess = rom.romanize("បារម្ភ")
    assert "barom" in [guess] + rom.learned_variants(guess) or "barom" in rom.variants("បារម្ភ")
