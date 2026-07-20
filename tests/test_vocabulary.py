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
        assert e.khmer and e.meaning
        assert 1 <= e.frequency <= 5
        assert isinstance(e.is_slang, bool)


def test_romanizations_parse_into_tuple():
    """The romanizations cell is split on whitespace into a tuple of spellings."""
    entries = load()
    by_khmer = {e.khmer: e for e in entries}
    assert by_khmer["ចឹង"].romanizations == ("jueng", "jg", "jhg")
    # Every entry's romanizations is a tuple (possibly empty).
    assert all(isinstance(e.romanizations, tuple) for e in entries)


def test_romanizations_optional_column(tmp_path):
    """A file without the romanizations column still loads (empty romanizations)."""
    csv_path = tmp_path / "no_rom.csv"
    csv_path.write_text(
        "khmer,meaning,frequency,is_slang,notes\nល្អ,good,5,false,\n",
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
        "khmer,meaning,frequency,is_slang,notes\n"
        "ល្អ,good,5,false,\n"
        "ល្អ,good again,4,false,\n",
    )
    with pytest.raises(VocabularyError, match="duplicate"):
        load(csv_path)


def test_rejects_out_of_range_frequency(tmp_path):
    csv_path = _write_csv(
        tmp_path / "freq.csv",
        "khmer,meaning,frequency,is_slang,notes\n"
        "ល្អ,good,9,false,\n",
    )
    with pytest.raises(VocabularyError, match="frequency"):
        load(csv_path)


def test_rejects_bad_boolean(tmp_path):
    csv_path = _write_csv(
        tmp_path / "bool.csv",
        "khmer,meaning,frequency,is_slang,notes\n"
        "ល្អ,good,5,maybe,\n",
    )
    with pytest.raises(VocabularyError, match="is_slang"):
        load(csv_path)


def test_rejects_missing_column(tmp_path):
    csv_path = _write_csv(
        tmp_path / "missing.csv",
        "khmer,meaning,frequency\nល្អ,good,5\n",
    )
    with pytest.raises(VocabularyError, match="missing required column"):
        load(csv_path)
