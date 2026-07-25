"""Tests for the vocabulary loader and the curated data file (step 1.2)."""

import pytest

from sing_khmer_engine.vocabulary import VocabEntry, VocabularyError, load


def test_seed_file_loads():
    """The committed seed vocabulary.csv parses and returns VocabEntry records."""
    entries = load()
    assert len(entries) > 0
    assert all(isinstance(e, VocabEntry) for e in entries)


def test_seed_entries_are_valid_and_unique():
    entries = load()
    khmer_keys = [e.khmer for e in entries]
    assert len(khmer_keys) == len(set(khmer_keys))  # no duplicates
    for e in entries:
        assert e.khmer  # meaning is optional
        assert 1 <= e.frequency <= 5
        assert isinstance(e.is_slang, bool)


def test_romanizations_parse_alternatives_and_plus(tmp_path):
    """Commas OR spaces separate alternatives; '+' marks a multi-word spelling."""
    csv_path = tmp_path / "rom.csv"
    csv_path.write_text(
        "khmer,frequency,is_slang,romanizations,notes\n"
        'ចឹង,4,true,"jueng, jg jhg",\n'          # comma AND space both = alternatives
        "ម្សិលមិញ,3,false,msel+minh,\n",          # '+' = one multi-word spelling
        encoding="utf-8",
    )
    entries = load(csv_path)
    assert entries[0].romanizations == ("jueng", "jg", "jhg")
    assert entries[1].romanizations == ("msel minh",)   # '+' becomes a spelling with a space


def test_real_data_has_romanizations():
    """Every entry's romanizations is a tuple, and the curated data is populated."""
    entries = load()
    assert all(isinstance(e.romanizations, tuple) for e in entries)
    assert any(e.romanizations for e in entries)


def test_romanizations_optional_column(tmp_path):
    """A file without the romanizations column still loads (empty romanizations)."""
    csv_path = tmp_path / "no_rom.csv"
    csv_path.write_text(
        "khmer,frequency,is_slang,notes\nល្អ,5,false,\n",
        encoding="utf-8",
    )
    entries = load(csv_path)
    assert entries[0].romanizations == ()


def _write_csv(path, rows):
    path.write_text(rows, encoding="utf-8")
    return path


def test_rejects_duplicate_khmer(tmp_path):
    csv_path = _write_csv(
        tmp_path / "dup.csv",
        "khmer,frequency,is_slang,notes\n"
        "ល្អ,5,false,\n"
        "ល្អ,4,false,\n",
    )
    with pytest.raises(VocabularyError, match="duplicate"):
        load(csv_path)


def test_rejects_out_of_range_frequency(tmp_path):
    csv_path = _write_csv(
        tmp_path / "freq.csv",
        "khmer,frequency,is_slang,notes\n"
        "ល្អ,9,false,\n",
    )
    with pytest.raises(VocabularyError, match="frequency"):
        load(csv_path)


def test_rejects_bad_boolean(tmp_path):
    csv_path = _write_csv(
        tmp_path / "bool.csv",
        "khmer,frequency,is_slang,notes\n"
        "ល្អ,5,maybe,\n",
    )
    with pytest.raises(VocabularyError, match="is_slang"):
        load(csv_path)


def test_rejects_missing_column(tmp_path):
    csv_path = _write_csv(
        tmp_path / "missing.csv",
        "khmer,frequency\nល្អ,5\n",
    )
    with pytest.raises(VocabularyError, match="missing required column"):
        load(csv_path)
