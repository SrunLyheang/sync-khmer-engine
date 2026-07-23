"""Vocabulary model and loader for the Sing Khmer mapping engine.

The vocabulary is the hand-curated list of supported Khmer words/phrases (roadmap
step 1.2). It is stored as a CSV so a native speaker can edit it in any spreadsheet,
and loaded here into validated ``VocabEntry`` records that later steps consume
(1.3 KCC breakdown, 1.4 phonetic rules, 1.7 lookup).

CSV columns: ``khmer, frequency, is_slang, romanizations, notes``
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

# Default location of the curated vocabulary file, relative to the repo root.
DEFAULT_VOCAB_PATH = Path(__file__).resolve().parents[2] / "data" / "vocabulary.csv"

REQUIRED_COLUMNS = ("khmer", "frequency", "is_slang")
_TRUE_VALUES = {"true", "1", "yes", "y"}
_FALSE_VALUES = {"false", "0", "no", "n"}


def parse_romanizations(raw: str) -> tuple[str, ...]:
    """Split a romanizations cell into alternative spellings.

    Alternatives are separated by **commas OR spaces** (so `jueng jg jhg` and
    `jueng, jg, jhg` are equivalent — three spellings). A genuine **multi-word
    spelling** (one spelling that's typed as two Latin words, like ``msel minh``
    for ម្សិលមិញ) is written with a **`+`**: ``msel+minh``. Each alternative is
    lowercased; duplicates dropped, order kept.
    """
    out: list[str] = []
    seen: set[str] = set()
    for alt in re.split(r"[,\s]+", (raw or "").strip()):
        alt = " ".join(alt.replace("+", " ").split()).lower()   # '+' -> multi-word space
        if alt and alt not in seen:
            seen.add(alt)
            out.append(alt)
    return tuple(out)


@dataclass(frozen=True)
class VocabEntry:
    """A single curated vocabulary entry.

    Attributes:
        khmer: The word/phrase in Khmer script (unique across the file).
        frequency: Rough commonness, an integer 1-5 (5 = most common).
        is_slang: True for casual/chat slang, False for an ordinary common word.
        romanizations: Sing Khmer (Latin) spellings for this word, parsed from a
            whitespace-separated cell. May be empty.
        notes: Optional freeform hints (usage, disambiguation, etc.).
    """

    khmer: str
    frequency: int
    is_slang: bool
    romanizations: tuple[str, ...] = ()
    notes: str = ""


class VocabularyError(ValueError):
    """Raised when the vocabulary file is malformed or fails validation."""


def _parse_bool(value: str, *, row_num: int) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise VocabularyError(
        f"row {row_num}: is_slang must be true/false, got {value!r}"
    )


def _parse_frequency(value: str, *, row_num: int) -> int:
    try:
        freq = int(value.strip())
    except ValueError:
        raise VocabularyError(
            f"row {row_num}: frequency must be an integer 1-5, got {value!r}"
        ) from None
    if not 1 <= freq <= 5:
        raise VocabularyError(
            f"row {row_num}: frequency must be between 1 and 5, got {freq}"
        )
    return freq


def load(path: str | Path = DEFAULT_VOCAB_PATH) -> list[VocabEntry]:
    """Load and validate the vocabulary CSV into a list of ``VocabEntry``.

    Args:
        path: Path to the vocabulary CSV. Defaults to ``data/vocabulary.csv``.

    Returns:
        The curated entries, in file order.

    Raises:
        FileNotFoundError: If the file does not exist.
        VocabularyError: If a required column is missing, a field is malformed,
            or a duplicate ``khmer`` key is found.
    """
    path = Path(path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise VocabularyError(f"{path}: file is empty (no header row)")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise VocabularyError(
                f"{path}: missing required column(s): {', '.join(missing)}"
            )

        entries: list[VocabEntry] = []
        seen: dict[str, int] = {}
        for row_num, row in enumerate(reader, start=2):  # row 1 is the header
            khmer = (row.get("khmer") or "").strip()
            if not khmer:
                raise VocabularyError(f"row {row_num}: khmer is required")
            if khmer in seen:
                raise VocabularyError(
                    f"row {row_num}: duplicate khmer entry {khmer!r} "
                    f"(first seen on row {seen[khmer]})"
                )
            seen[khmer] = row_num

            entries.append(
                VocabEntry(
                    khmer=khmer,
                    frequency=_parse_frequency(row["frequency"], row_num=row_num),
                    is_slang=_parse_bool(row["is_slang"], row_num=row_num),
                    romanizations=parse_romanizations(row.get("romanizations") or ""),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return entries
