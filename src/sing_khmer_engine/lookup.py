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
from dataclasses import dataclass, replace

from .english import load_english
from .fuzzy import levenshtein, within
from .reverse_index import Candidate, build_index
from .romanizer import Romanizer
from .vocabulary import VocabEntry, load

# Splits a whitespace token into (leading punctuation, core spelling, trailing punctuation).
_TOKEN_RE = re.compile(r"^(\W*)(.*?)(\W*)$")

# A run of 2+ spaces in the input commits a real space in the output (single space
# stays a word boundary). Matches the iOS double-space habit — no extra keys.
_DOUBLE_SPACE_RE = re.compile(r" {2,}")

# Khmer repetition sign ( លេខទោ / ៗ): a repeated word renders as `word` + ៗ.
_REPEAT_SIGN = "ៗ"

# Segmentation scoring knobs.
_LEN_WEIGHT = 3.0        # reward for covering more characters with a real spelling
_UNKNOWN_PENALTY = 2.0   # cost per character left unmatched
_WORD_COST = 6.0         # per-word cost so one whole word beats splitting it in two

# Confidence gate: if a single run-together token can only be "matched" by chopping
# it into pieces while leaving at least this fraction of its characters unmatched,
# the match is almost certainly accidental gibberish — pass the token through as-is
# (e.g. "javascript" stays "javascript" instead of becoming ចាសវ៉ា script). A genuine
# Sing Khmer token (nhslbong) leaves zero characters unmatched, so it is never gated.
_PASSTHROUGH_UNMATCHED = 0.34


@dataclass(frozen=True)
class Segment:
    """One piece of a decoded message: a matched spelling or passed-through text."""

    surface: str                       # the Latin text this segment covers
    candidates: tuple[Candidate, ...]  # empty => unknown / passed through unchanged
    lead: str = ""                     # leading punctuation to keep
    trail: str = ""                    # trailing punctuation to keep
    display: str | None = None         # explicit rendering override (e.g. ៗ for a repeat)
    space: bool = False                # a literal space committed by a double-space

    @property
    def matched(self) -> bool:
        return bool(self.candidates)

    @property
    def best(self) -> str:
        if self.space:
            return " "
        khmer = self.display if self.display is not None else (
            self.candidates[0].khmer if self.candidates else self.surface
        )
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
        use_english: bool = True,
    ) -> None:
        self.vocab = vocab if vocab is not None else load()
        # The romanizer generates plausible spelling variants so a reasonable spelling
        # nobody has typed yet still matches (coverage for the "everyone spells it
        # differently" reality). Variants are scored below collected spellings.
        self.romanizer = Romanizer(self.vocab)
        self.index = build_index(
            self.vocab, self.romanizer.variants if use_generated else None
        )
        self._max_key_len = max((len(k) for k in self.index), default=1)
        # Known Khmer words, used to spot a reduplication (W+W -> W ៗ).
        self._khmer_words = {entry.khmer for entry in self.vocab}
        # Common English words, for code-switching (pass English through, not Khmer).
        self._english = load_english() if use_english else frozenset()

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
    def _key_score(self, key: str) -> float:
        # Reward frequency + coverage; a per-word cost so a single whole word
        # (e.g. បង្រៀន) beats splitting it into two (បង + រៀន).
        return self.index[key][0].score + _LEN_WEIGHT * len(key) - _WORD_COST

    def _merge_multi_word(self, tokens: list[str]) -> list[str]:
        """Merge adjacent tokens that together form a multi-word index key.

        Scans tokens left-to-right, greedily joining consecutive tokens whose
        space-joined form is a known spelling.  E.g. ``['msel', 'minh']`` becomes
        ``['msel minh']`` when ``msel minh`` is in the reverse index.
        """
        if not tokens:
            return []
        merged: list[str] = []
        i = 0
        while i < len(tokens):
            best_len = 1
            for j in range(i + 1, min(i + 4, len(tokens) + 1)):
                candidate = " ".join(tokens[i:j])
                if candidate.lower() in self.index:
                    best_len = j - i
            merged.append(" ".join(tokens[i:i + best_len]))
            i += best_len
        return merged

    def _segment_kbest(self, lower: str, k: int) -> list[list[tuple[int, int, str | None]]]:
        """Top-`k` ways to cover `lower` with known spellings (Viterbi k-best).

        Each result is a list of spans (start, end, key-or-None); a key span is an
        exact index hit (may contain spaces = multi-word spelling), None spans are
        single non-matching characters. Alternatives let the caller offer the user
        different readings (compound word vs. split)."""
        n = len(lower)
        # dp[i] = list of (score, prev_i, prev_rank, key) sorted best-first.
        dp: list[list[tuple[float, int, int, str | None]]] = [[] for _ in range(n + 1)]
        dp[0] = [(0.0, -1, -1, None)]
        for i in range(1, n + 1):
            cands: list[tuple[float, int, int, str | None]] = []
            step = 0.0 if lower[i - 1] == " " else -_UNKNOWN_PENALTY
            for rank, (sc, *_r) in enumerate(dp[i - 1]):
                cands.append((sc + step, i - 1, rank, None))
            for j in range(max(0, i - self._max_key_len), i):
                if not dp[j]:
                    continue
                sub = lower[j:i]
                if sub not in self.index:
                    continue
                if len(sub) == 1 and not (
                    (j == 0 or lower[j - 1] == " ") and (i == n or lower[i] == " ")
                ):
                    continue
                ks = self._key_score(sub)
                for rank, (sc, *_r) in enumerate(dp[j]):
                    cands.append((sc + ks, j, rank, sub))
            cands.sort(key=lambda x: -x[0])
            dp[i] = cands[:k]

        paths: list[list[tuple[int, int, str | None]]] = []
        for start_rank in range(len(dp[n])):
            spans: list[tuple[int, int, str | None]] = []
            i, rank = n, start_rank
            while i > 0:
                _sc, pj, pr, key = dp[i][rank]
                spans.append((pj, i, key))
                i, rank = pj, pr
            spans.reverse()
            paths.append(spans)
        return paths

    @staticmethod
    def _is_strong_match(inside, ts: int, te: int) -> bool:
        """True if the whole token is covered by a single exact spelling — a strong,
        confident Khmer match (as opposed to a pile of little pieces)."""
        return len(inside) == 1 and inside[0][2] is not None and \
            inside[0][0] == ts and inside[0][1] == te

    def _low_confidence_tokens(self, lower: str, spans) -> list[tuple[int, int]]:
        """Whitespace tokens that should pass through as Latin instead of being turned
        into Khmer: either a word the engine can only match by chopping into gibberish
        (mostly-unmatched), or a genuine English word that isn't a strong Khmer match
        (code-switching). A token matched by a spelling that legitimately spans the
        space (a multi-word key) is never gated."""
        forced: list[tuple[int, int]] = []
        for m in re.finditer(r"\S+", lower):
            ts, te = m.start(), m.end()
            if any(j < te and i > ts and (j < ts or i > te) for j, i, key in spans):
                continue                                  # a spelling crosses this token's edge
            inside = [(j, i, key) for j, i, key in spans if ts <= j and i <= te]
            strong = self._is_strong_match(inside, ts, te)
            # English that isn't a strong Khmer match -> keep it as English.
            if lower[ts:te] in self._english and not strong:
                forced.append((ts, te))
                continue
            unmatched = sum(i - j for j, i, key in inside if key is None)
            matched = sum(1 for _j, _i, key in inside if key is not None)
            if matched and unmatched and unmatched / (te - ts) >= _PASSTHROUGH_UNMATCHED:
                forced.append((ts, te))
        return forced

    def _spans_to_segments(self, text: str, spans, *, limit: int) -> list[Segment]:
        spans = list(spans)
        lower = text.lower()
        forced = self._low_confidence_tokens(lower, spans)
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
                # Single-character fragments should pass through — they are
                # leftovers the Viterbi decoder couldn't match, not intentional
                # words.  (Standalone single-char tokens like `b` typed alone
                # DO match via _segment_kbest — this path only fires for
                # unmatched fragments left inside a longer token.)
                if len(core) == 1:
                    segments.append(Segment(tok, ()))
                    continue
                cands = tuple(self.convert(core, limit=limit))
                segments.append(Segment(core, cands, lead, trail))

        idx = 0
        while idx < len(spans):
            j, i, key = spans[idx]
            region = next((r for r in forced if r[0] <= j and i <= r[1]), None)
            if region is not None:                       # low-confidence token -> passthrough
                flush_raw(region[0])
                segments.append(Segment(text[region[0]:region[1]], ()))
                while idx < len(spans) and region[0] <= spans[idx][0] and spans[idx][1] <= region[1]:
                    idx += 1
                continue
            if key is None:
                if raw_start is None:
                    raw_start = j
            else:
                flush_raw(j)
                surface = text[j:i]
                cands = list(self.index[key][:limit])
                # If a whole-token spelling is also a real English word, offer the
                # English original as the LAST option (hidden until expanded, never
                # auto-picked) — e.g. "computer" -> កុំព្យូទ័រ … or English "computer".
                boundary = (j == 0 or lower[j - 1] == " ") and (i == len(text) or lower[i] == " ")
                if boundary and surface.lower() in self._english:
                    cands.append(Candidate(surface, 0.0, "english"))
                segments.append(Segment(surface, tuple(cands)))
            idx += 1
        flush_raw(len(text))
        return segments

    def _reduplication_base(self, khmer: str) -> str | None:
        """If `khmer` is a word repeated twice (e.g. មួយមួយ = មួយ+មួយ) whose half is a
        known word, return that half; otherwise None. Lets មួយមួយ render as មួយ ៗ."""
        if len(khmer) % 2 == 0:
            half = khmer[: len(khmer) // 2]
            if khmer[len(khmer) // 2:] == half and half in self._khmer_words:
                return half
        return None

    def _apply_repetition(self, segments: list[Segment]) -> list[Segment]:
        """Render a repeated word with the Khmer repetition sign ៗ instead of writing
        the word twice: two adjacent identical words (`muy muy`) or a single doubled
        entry (មួយមួយ) both become `word` + ៗ. The doubled form stays available as an
        alternative reading (see `readings`)."""
        out: list[Segment] = []
        prev_word: str | None = None
        for s in segments:
            word = s.candidates[0].khmer if s.matched else None
            can_fold = word is not None and s.display is None and not s.lead and not s.trail
            base = self._reduplication_base(word) if can_fold else None
            if can_fold and base is not None:                      # doubled entry (មួយមួយ)
                out.append(replace(s, display=base + _REPEAT_SIGN))
                prev_word = base
            elif can_fold and word == prev_word:                   # two adjacent (muy muy)
                out.append(replace(s, display=_REPEAT_SIGN))
                prev_word = word
            else:
                out.append(s)
                prev_word = word
        return out

    def decode(self, text: str, *, limit: int = 5) -> list[Segment]:
        """Decode a whole message into matched/unknown segments (best reading).

        A run of 2+ spaces commits a real space (single space stays a word boundary);
        a repeated word folds to the ៗ repetition sign.

        Tokens separated by single spaces are segmented independently so spellings
        never fragment across word boundaries.  Adjacent tokens that form a multi-word
        spelling (e.g. ``msel minh``) are re-merged first so those still match."""
        segments: list[Segment] = []
        for idx, part in enumerate(_DOUBLE_SPACE_RE.split(text)):
            if idx > 0:                                    # gap between parts = real space
                segments.append(Segment(" ", (), space=True))
            if not part:
                continue
            tokens = self._merge_multi_word(part.split())
            for token in tokens:
                lower = token.lower()
                paths = self._segment_kbest(lower, 1)
                spans = paths[0] if paths else []
                # If the token isn't a direct index key AND the best Viterbi
                # path left unmatched fragments, the engine can only force a
                # partial match.  Pass the whole token through instead of
                # producing a mix like sa+ខ្ញុំ+b (e.g. "sab" → "sa" matched +
                # "b" fragment → just keep "sab" as-is).
                if lower not in self.index and any(key is None for _, _, key in spans):
                    segments.append(Segment(token, ()))
                else:
                    segments.extend(self._spans_to_segments(token, spans, limit=limit))
        return self._apply_repetition(segments)

    @staticmethod
    def join_segments(segments: list[Segment]) -> str:
        """Render decoded segments the way Khmer is actually written: consecutive
        Khmer words run together with NO space (ខ្ញុំស្រឡាញ់បង), while passed-through
        Latin/English words keep spaces around them and punctuation attaches directly.
        A literal-space segment forces a single space between neighbours."""
        result = ""
        prev_khmer = False
        attach_next = False                       # after a real space, attach directly
        for s in segments:
            if s.space:
                if result and not result.endswith(" "):
                    result += " "
                prev_khmer, attach_next = False, True
                continue
            is_khmer = s.matched
            is_punct = (not is_khmer) and bool(s.surface) and not any(
                ch.isalnum() for ch in s.surface
            )
            piece = s.best
            if not result or attach_next:
                result += piece
            elif is_punct or (prev_khmer and is_khmer):
                result += piece                       # no space
            else:
                result += " " + piece                 # space around non-Khmer
            prev_khmer, attach_next = is_khmer, False
        return result

    def readings(self, text: str, *, k: int = 3) -> list[str]:
        """Up to `k` distinct whole-message readings, best first — so the UI can let
        the user switch between e.g. បង្រៀន (one word) and បងរៀន (two words), or a folded
        repetition (មួយៗ) and its doubled form (មួយមួយ)."""
        out: list[str] = []
        base = self.decode(text)
        out.append(self.join_segments(base))
        if any(s.display == _REPEAT_SIGN or (s.display or "").endswith(_REPEAT_SIGN)
               for s in base):                            # offer the un-folded doubled form
            doubled = [replace(s, display=None) if s.display and s.display.endswith(_REPEAT_SIGN)
                       else s for s in base]
            reading = self.join_segments(doubled)
            if reading not in out:
                out.append(reading)
        if not _DOUBLE_SPACE_RE.search(text):             # compound<->split alternatives
            for spans in self._segment_kbest(text.lower(), k * 2):
                segs = self._apply_repetition(self._spans_to_segments(text, spans, limit=1))
                reading = self.join_segments(segs)
                if reading not in out:
                    out.append(reading)
                if len(out) >= k:
                    break
        return out[:k] if len(out) > k else out

    def convert_sentence_text(self, text: str) -> str:
        """Top-pick Khmer for a whole message (Khmer words run together, no spaces)."""
        return self.join_segments(self.decode(text))

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
