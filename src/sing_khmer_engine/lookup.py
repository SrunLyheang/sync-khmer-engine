"""Core lookup: Latin (Sing Khmer) input -> ranked Khmer candidates (step 1.7).

`Engine` ties the pieces together: it loads the vocabulary, builds the phonetic
rules and the reverse index, and answers `convert(text)` with a ranked list of
Khmer candidates. Exact-match only for now; fuzzy/edit-distance fallback for
non-exact input is step 1.8.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .fuzzy import levenshtein, within
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


@dataclass(frozen=True)
class Diagnosis:
    """Why a spelling did or didn't match — see `Engine.diagnose()`."""

    text: str                          # original input
    key: str                           # normalized (stripped/lowercased) input
    outcome: str                       # "exact" | "fuzzy" | "no_match"
    candidates: list[Candidate]        # populated for "exact"/"fuzzy"
    closest_key: str | None            # populated for "no_match": nearest known key
    closest_distance: int | None       # raw edit distance to closest_key


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

    def convert(
        self, text: str, *, limit: int = 5, fuzzy: bool = True
    ) -> list[Candidate]:
        """Return up to `limit` ranked Khmer candidates for a Latin spelling.

        Tries an exact match first; if none and `fuzzy` is on, falls back to the
        closest known spellings by edit distance. Empty list means no match at all.
        """
        key = text.strip().lower()
        if not key:
            return []
        exact = self.index.get(key)
        if exact:
            return exact[:limit]
        if not fuzzy:
            return []
        return self._fuzzy(key, limit=limit)

    def _fuzzy(self, key: str, *, limit: int) -> list[Candidate]:
        """Closest known spellings by edit distance, ranked by (distance, frequency)."""
        threshold = 1 if len(key) <= 3 else 2
        best: dict[str, tuple[int, float]] = {}  # khmer -> (distance, score)
        for ikey, cands in self.index.items():
            d = within(key, ikey, threshold)
            if d is None:
                continue
            for c in cands:
                cur = best.get(c.khmer)
                if cur is None or (d, -c.score) < (cur[0], -cur[1]):
                    best[c.khmer] = (d, c.score)
        ranked = sorted(best.items(), key=lambda kv: (kv[1][0], -kv[1][1], kv[0]))
        return [
            Candidate(khmer, round(score / (1.0 + d), 3), "fuzzy")
            for khmer, (d, score) in ranked
        ][:limit]

    def diagnose(self, text: str) -> "Diagnosis":
        """Explain *why* a spelling did or didn't match — for finding coverage gaps.

        Unlike `convert()`, this ignores the fuzzy distance threshold: if there's no
        exact or in-threshold fuzzy hit, it still reports the single closest known
        spelling and its raw edit distance, so "missing word entirely" can be told
        apart from "word exists, spelling is just far off".
        """
        key = text.strip().lower()
        exact = self.index.get(key, [])
        if exact:
            return Diagnosis(text, key, "exact", exact, None, None)

        fuzzy_hits = self._fuzzy(key, limit=5)
        if fuzzy_hits:
            return Diagnosis(text, key, "fuzzy", fuzzy_hits, None, None)

        # Nothing within threshold — find the single closest key anyway, unbounded.
        closest_key, closest_dist = None, None
        for ikey in self.index:
            d = levenshtein(key, ikey)
            if closest_dist is None or d < closest_dist:
                closest_key, closest_dist = ikey, d
        return Diagnosis(text, key, "no_match", [], closest_key, closest_dist)

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
