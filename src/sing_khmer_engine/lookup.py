"""Core lookup: Latin (Sing Khmer) input -> ranked Khmer candidates (step 1.7).

`Engine` ties the pieces together: it loads the vocabulary, builds the phonetic
rules and the reverse index, and answers `convert(text)` with a ranked list of
Khmer candidates. Exact-match only for now; fuzzy/edit-distance fallback for
non-exact input is step 1.8.
"""

from __future__ import annotations

from .phonetic_rules import build_rules
from .reverse_index import Candidate, build_index
from .vocabulary import VocabEntry, load


class Engine:
    """The Sing Khmer conversion engine."""

    def __init__(
        self,
        vocab: list[VocabEntry] | None = None,
        *,
        use_generated: bool = True,
    ) -> None:
        self.vocab = vocab if vocab is not None else load()
        self.rules = build_rules(self.vocab)
        self.index = build_index(
            self.vocab, self.rules if use_generated else None
        )

    def convert(self, text: str, *, limit: int = 5) -> list[Candidate]:
        """Return up to `limit` ranked Khmer candidates for a Latin spelling.

        Empty list means no exact match (fuzzy matching arrives in step 1.8).
        """
        key = text.strip().lower()
        return self.index.get(key, [])[:limit]


def lookup(text: str, *, engine: Engine | None = None, limit: int = 5) -> list[Candidate]:
    """Convenience one-shot lookup. Reuse an `Engine` for repeated queries."""
    return (engine or Engine()).convert(text, limit=limit)
