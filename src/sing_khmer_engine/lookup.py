"""Core lookup + segmentation: Latin (Sing Khmer) input -> ranked Khmer (steps 1.7–1.8).

`Engine` loads the vocabulary, builds the phonetic rules and the reverse index, and
answers:
  - `convert(text)`   — one spelling -> ranked Khmer candidates (exact, else fuzzy).
  - `decode(text)`    — a whole message -> a sequence of segments, each matched Khmer
                        or passed-through. Uses a segmentation decoder so it works
                        WITH OR WITHOUT spaces between words, and matches multi-word
                        spellings (e.g. `msel minh` -> ម្សិលមិញ) as single units.
  - `diagnose(text)`  — explains why one spelling did/didn't match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .fuzzy import levenshtein, within
from .phonetic_rules import build_rules
from .reverse_index import Candidate, build_index
from .vocabulary import VocabEntry, load

# Splits a whitespace token into (leading punctuation, core spelling, trailing punctuation).
_TOKEN_RE = re.compile(r"^(\W*)(.*?)(\W*)$")

# Segmentation scoring knobs.
_LEN_WEIGHT = 3.0        # reward for covering more characters with a real spelling
_UNKNOWN_PENALTY = 2.0   # cost per character left unmatched


@dataclass(frozen=True)
class Segment:
    """One piece of a decoded message: a matched spelling or passed-through text."""

    surface: str                       # the Latin text this segment covers
    candidates: tuple[Candidate, ...]  # empty => unknown / passed through unchanged
    lead: str = ""                     # leading punctuation to keep
    trail: str = ""                    # trailing punctuation to keep

    @property
    def matched(self) -> bool:
        return bool(self.candidates)

    @property
    def best(self) -> str:
        khmer = self.candidates[0].khmer if self.candidates else self.surface
        return f"{self.lead}{khmer}{self.trail}"


@dataclass(frozen=True)
class Diagnosis:
    """Why a spelling did or didn't match — see `Engine.diagnose()`."""

    text: str
    key: str
    outcome: str                       # "exact" | "fuzzy" | "no_match"
    candidates: list[Candidate]
    closest_key: str | None
    closest_distance: int | None


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
        self.index = build_index(self.vocab, self.rules if use_generated else None)
        self._max_key_len = max((len(k) for k in self.index), default=1)

    # ---- single-spelling lookup (exact, then fuzzy) --------------------------------
    def convert(self, text: str, *, limit: int = 5, fuzzy: bool = True) -> list[Candidate]:
        """Ranked Khmer candidates for one Latin spelling. Empty = no match."""
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
        threshold = 1 if len(key) <= 3 else 2
        best: dict[str, tuple[int, float]] = {}
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

    # ---- whole-message decoding (segmentation) ------------------------------------
    def _segment_spans(self, lower: str) -> list[tuple[int, int, str | None]]:
        """Best cover of `lower` by known spellings, via dynamic programming.

        Returns spans (start, end, key-or-None). A key span is an exact index hit
        (may contain spaces = a multi-word spelling); None spans are single
        non-matching characters. Works with or without spaces because spaces are
        just free separators. Single-character spellings only match as whole
        space-delimited tokens (so `b`/`s` don't chop longer runs)."""
        n = len(lower)
        NEG = float("-inf")
        dp = [NEG] * (n + 1)
        dp[0] = 0.0
        back: list[tuple[int, str | None]] = [(0, None)] * (n + 1)
        for i in range(1, n + 1):
            # non-matching char (space = free, other = penalty) — always available
            step = 0.0 if lower[i - 1] == " " else -_UNKNOWN_PENALTY
            if dp[i - 1] + step > dp[i]:
                dp[i] = dp[i - 1] + step
                back[i] = (i - 1, None)
            # known spelling ending at i
            for j in range(max(0, i - self._max_key_len), i):
                if dp[j] <= NEG:
                    continue
                sub = lower[j:i]
                cands = self.index.get(sub)
                if not cands:
                    continue
                if len(sub) == 1 and not (
                    (j == 0 or lower[j - 1] == " ") and (i == n or lower[i] == " ")
                ):
                    continue
                score = dp[j] + cands[0].score + _LEN_WEIGHT * len(sub)
                if score > dp[i]:
                    dp[i] = score
                    back[i] = (j, sub)
        spans: list[tuple[int, int, str | None]] = []
        i = n
        while i > 0:
            j, key = back[i]
            spans.append((j, i, key))
            i = j
        spans.reverse()
        return spans

    def decode(self, text: str, *, limit: int = 5) -> list[Segment]:
        """Decode a whole message into matched/unknown segments (see class docstring)."""
        lower = text.lower()
        spans = self._segment_spans(lower)
        segments: list[Segment] = []
        raw_start: int | None = None

        def flush_raw(end: int) -> None:
            nonlocal raw_start
            if raw_start is None:
                return
            chunk = text[raw_start:end]
            raw_start = None
            for m in re.finditer(r"\S+", chunk):        # fuzzy-match leftover words
                tok = m.group(0)
                lead, core, trail = _TOKEN_RE.match(tok).groups()
                if not core:
                    segments.append(Segment(tok, ()))    # pure punctuation
                    continue
                cands = tuple(self.convert(core, limit=limit))
                segments.append(Segment(core, cands, lead, trail))

        for j, i, key in spans:
            if key is None:
                if raw_start is None:
                    raw_start = j
            else:
                flush_raw(j)
                segments.append(Segment(text[j:i], tuple(self.index[key][:limit])))
        flush_raw(len(text))
        return segments

    def convert_sentence(self, text: str, *, limit: int = 5) -> list[Segment]:
        """Decode a whole message (alias for `decode`, works with/without spaces)."""
        return self.decode(text, limit=limit)

    def convert_sentence_text(self, text: str) -> str:
        """Top-pick Khmer for a whole message, segments joined with spaces."""
        return " ".join(s.best for s in self.decode(text))

    # ---- diagnostics --------------------------------------------------------------
    def diagnose(self, text: str) -> Diagnosis:
        """Explain why one spelling did/didn't match (ignores the fuzzy threshold
        when reporting the closest known spelling)."""
        key = text.strip().lower()
        exact = self.index.get(key, [])
        if exact:
            return Diagnosis(text, key, "exact", exact, None, None)
        fuzzy_hits = self._fuzzy(key, limit=5)
        if fuzzy_hits:
            return Diagnosis(text, key, "fuzzy", fuzzy_hits, None, None)
        closest_key, closest_dist = None, None
        for ikey in self.index:
            d = levenshtein(key, ikey)
            if closest_dist is None or d < closest_dist:
                closest_key, closest_dist = ikey, d
        return Diagnosis(text, key, "no_match", [], closest_key, closest_dist)


def lookup(text: str, *, engine: Engine | None = None, limit: int = 5) -> list[Candidate]:
    """Convenience one-shot lookup. Reuse an `Engine` for repeated queries."""
    return (engine or Engine()).convert(text, limit=limit)
