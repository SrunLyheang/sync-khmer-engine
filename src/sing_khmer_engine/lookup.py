"""Core lookup: Latin (Sing Khmer) input -> ranked Khmer candidates (step 1.7).

`Engine` ties the pieces together: it loads the vocabulary, builds the phonetic
rules and the reverse index, and answers `convert(text)` with a ranked list of
Khmer candidates. Exact-match only for now; fuzzy/edit-distance fallback for
non-exact input is step 1.8.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .phonetic_rules import build_rules
from .reverse_index import Candidate, build_index
from .vocabulary import VocabEntry, load

# Splits a whitespace token into (leading punctuation, core spelling, trailing punctuation),
# so "bong!" or "(nh)" convert the core and keep the punctuation.
_TOKEN_RE = re.compile(r"^(\W*)(.*?)(\W*)$")


@dataclass(frozen=True)
class WordResult:
    """One word of a sentence: the original token and its ranked candidates."""

    token: str                       # original token, punctuation included
    core: str                        # the spelling that was looked up
    candidates: tuple[Candidate, ...]
    lead: str = ""                   # leading punctuation to keep
    trail: str = ""                  # trailing punctuation to keep

    @property
    def matched(self) -> bool:
        return bool(self.candidates)

    @property
    def best(self) -> str:
        """Best Khmer rendering (or the original core if nothing matched), with
        surrounding punctuation preserved."""
        khmer = self.candidates[0].khmer if self.candidates else self.core
        return f"{self.lead}{khmer}{self.trail}"


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

    def convert_sentence(self, text: str, *, limit: int = 5) -> list[WordResult]:
        """Convert a whitespace-separated sentence, word by word.

        Each word keeps its ranked candidates (so a UI can offer choices) and any
        surrounding punctuation. Unknown words fall through unchanged.
        """
        results: list[WordResult] = []
        for token in text.split():
            lead, core, trail = _TOKEN_RE.match(token).groups()
            cands = tuple(self.convert(core, limit=limit)) if core else ()
            results.append(WordResult(token, core, cands, lead, trail))
        return results

    def convert_sentence_text(self, text: str) -> str:
        """The top-pick Khmer for a whole sentence, joined with spaces."""
        return " ".join(w.best for w in self.convert_sentence(text))


def lookup(text: str, *, engine: Engine | None = None, limit: int = 5) -> list[Candidate]:
    """Convenience one-shot lookup. Reuse an `Engine` for repeated queries."""
    return (engine or Engine()).convert(text, limit=limit)
