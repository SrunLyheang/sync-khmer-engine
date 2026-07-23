# Refactor & dataset cleanup (Phase 4)

This pass removed dead code, tidied the data schema, and added a data linter, without
changing any user-visible conversion behavior (the test suite stays green). It sits on
top of the earlier Phase 1–3 work (typing UX, the confidence gate, English detection).

## Code

- **Removed the dead `aligned` phonetic-rules path.** `phonetic_rules.py` had an
  experimental "two-KCC alignment" heuristic gated behind `include_aligned=False` that
  was never enabled anywhere. Deleted it along with its helpers (`_best_prefix`,
  `_best_suffix`) and the iteration loop. Rules are now derived purely from the
  unambiguous **direct** evidence (single-KCC words), which is all the engine ever used.
- **Dropped the now-single-valued `Rule.source` field.** With `aligned` gone every rule
  was `"direct"`, so the field carried no information. `reverse_index.py` never read it.
- **Removed the `convert_sentence` alias** (a one-line pass-through to `decode`). Callers
  use `decode` / `convert_sentence_text` directly.

## Data (`data/vocabulary.csv`)

- **Dropped the `meaning` column.** It had been empty for every one of the 869 rows, so
  it was pure schema weight. The columns are now `khmer, frequency, is_slang,
  romanizations, notes`. The loader, `data/README.md`, and the tests were updated to
  match; `VocabEntry` no longer has a `meaning` field.
- **Cleaned romanization artifacts:**
  - trailing dots — `kort.` → `kort`, `yun.` → `yun`
  - non-ASCII letters — `café` → `cafe`
  - a hidden zero-width space inside `khoa`
  - a double-quote typo — `p"o` → `p'o` (the apostrophe marks the អ onset, as in
    `s'aek`, `p'aem`)
  - de-duplicated alternatives and normalized every cell to a canonical `", "` separator.
- **Kept the apostrophe** as a legitimate spelling device (it consistently marks the អ
  glottal onset in clusters like ស្អែក `s'aek`, ផ្អែម `p'aem`), and kept the `+`
  multi-word convention untouched.

## New: `scripts/check_vocab.py`

A content linter for the vocabulary that runs *after* the loader's schema validation and
catches the kinds of problems the loader can't:

- **ERROR** — non-ASCII letters, stray punctuation (anything but latin letters, spaces
  from `+`, and the allowed apostrophe), or zero-width/control characters in a cell.
- **WARN** — duplicate alternatives in one row, or a `+` multi-word spelling whose parts
  are *also* listed as single alternatives of the same word (a likely space-vs-`+`
  mix-up).

It exits non-zero when any ERROR is found, so it can gate CI. On the cleaned data it
reports **0 errors, 0 warnings**.

## Considered but deliberately left alone

- **The JS duplicated between `scripts/serve.py` and `scripts/build_web_demo.py`.** They
  share a decoder port, but one is a live server using the real Python engine and the
  other is a fully offline static file with the decoder reimplemented in JS. Extracting a
  shared module would mean a build step and real regression risk for a testing-only aid,
  so the duplication stays — both are kept in sync by hand and both are verified (pytest
  for the engine, `node` for the offline port).
