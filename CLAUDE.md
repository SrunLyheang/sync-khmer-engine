# Sing Khmer — Project Memory

> This file is read automatically by Claude Code at the start of every session in this repo. Keep "Current Position" updated as you complete steps.

## The Problem

Cambodians commonly type Khmer using Latin letters phonetically ("Sing Khmer") instead of Khmer script — e.g. writing "jg" or "jhg" for ចឹង. This happens in chat apps, TikTok, YouTube search, etc. The core challenge: there's no standardized romanization for casual chat Khmer, so the same word gets spelled multiple different ways by different people.

## The Idea

An app/keyboard that auto-converts Sing Khmer (romanized input) into proper Khmer script as the user types, starting narrow and expanding over time.

## Decisions Made

- **Platforms:** iOS and Android first (as custom keyboards). Browser extension is a later phase. Desktop native (Windows/Mac system-level IME) is out of scope for now.
- **Conversion UX:** Show a ranked suggestion list to pick from as the user types (like Google Input Tools) — not silent auto-conversion.
- **Scope:** Casual chat slang/common words first, not full Khmer vocabulary. Expand coverage as the codebase matures.
- **Build sequence:** (1) Python mapping-engine prototype → (2) Android keyboard → (3) iOS keyboard extension → (4) Browser extension. Chosen because the developer is new to native mobile dev.
- **Data strategy:** the developer is a native Khmer speaker and will personally curate the dictionary — no dependency on outside crowdsourcing to bootstrap.

## Mapping Engine Design (Phase 1)

- **Core unit is the Khmer Character Cluster (KCC)** — the inseparable syllable-level unit (a vowel sign can never stand alone; it always attaches to a consonant). Mapping single letters in isolation produces noise; work at the KCC level instead.
- **Three-part data model:**
  1. `phonetic_rules` — KCC → list of plausible Latin spellings, each with a confidence weight
  2. `vocabulary` — supported Khmer words/phrases, each broken into KCCs, tagged with frequency + "is casual slang"
  3. `reverse_index` (generated, not hand-built) — Cartesian product of each word's KCC spelling options, producing every plausible full romanization → Khmer word + confidence score. This is the actual runtime lookup table.
- **Ambiguity handling:**
  - Multiple Khmer words sharing a romanization (homophones) → rank by frequency + confidence
  - One word, many valid romanizations → solved by generating all combinations in the reverse index
  - No exact match → fall back to edit-distance/fuzzy matching against reverse-index keys
- **Vocabulary source:** start with a hand-curated casual/chat word list (not khmerlbdict — that's Bible/place-name/village-name frequency data, mismatched for chat slang). Bring in khmerlbdict later when expanding past slang.

## Known Technical Challenges

- No standardized romanization for informal chat Khmer — needs fuzzy matching + real usage data over time, not just fixed rules
- Khmer script is an abugida — words aren't space-delimited, complicating word-boundary detection
- iOS keyboard extensions are sandboxed — need "Allow Full Access" for network/large dictionary access; Apple reviews keyboard apps strictly
- Android's `InputMethodService` is more open, with more prior art, than iOS

## Useful Existing Resources (not yet vetted for license/quality)

- `IDRI-LAB/Khmer-NLP-Tools` — includes an existing Khmer→Latin romanizer; useful as reference logic even though it's the inverse direction
- `seanghay/awesome-khmer-language` — curated list: word segmenters, spell checker (`Socret360/akara-python`), text normalizer (`seanghay/tha`), pronunciation toolkit (`seanghay/khmerpronounce`)
- `VietHoang1512/khmer-nltk` — tokenizer/segmenter/POS-tagger
- `sbbic/khmerlbdict` — frequency wordlist (Bible/place/village names — save for later, general-vocabulary phase)
- `ye-kyaw-thu/khPOS` — Khmer POS-tagged corpus

## Not Yet Decided

- Exact format/structure of the phonetic rule table (beyond the 3-part model above)
- How ranking/scoring of multiple candidates will work in detail
- App name/branding
- Monetization/distribution plan

---

## Roadmap

### Phase 1 — Mapping Engine Prototype (Python, no mobile dev)
Goal: prove romanized→Khmer matching works before building any UI.

- [x] 1.1 Set up a basic Python project (repo, venv, folder structure)
- [x] 1.2 Hand-curate ~100–200 casual/chat words in Khmer script (257 words, team-curated)
- [x] 1.3 Break each vocabulary word into KCCs
- [~] 1.4 Build the `phonetic_rules` table (KCC → Latin spellings + confidence weights) — exact
      rules done (49/264 KCCs from single-KCC words); rest deferred (see finding below)
- [ ] 1.5 Skim IDRI-LAB's romanizer for reference logic
- [x] 1.6 Script to generate the `reverse_index` programmatically
- [x] 1.7 Core lookup function: Latin input → ranked Khmer candidates
- [ ] 1.8 Fuzzy/edit-distance fallback for non-exact matches
- [ ] 1.9 Test against real romanized chat examples, measure accuracy
- [ ] 1.10 Iterate on rules/weights based on failures

**Exit criteria:** correct Khmer word lands in the top 3 candidates for most test examples.

### Phase 2 — Android Keyboard Shell (Kotlin)
- [ ] 2.1 Minimal `InputMethodService` project in Android Studio
- [ ] 2.2 Study/fork an open-source keyboard (e.g. Simple Keyboard) as reference
- [ ] 2.3 Basic QWERTY layout outputting raw Latin text first
- [ ] 2.4 Port/bundle the Phase 1 lookup logic (Kotlin port or bundled JSON)
- [ ] 2.5 Suggestion bar UI with ranked candidates
- [ ] 2.6 Candidate selection → insert Khmer text into focused app
- [ ] 2.7 Test in real target apps (TikTok, YouTube, Messenger)
- [ ] 2.8 Distribute for personal/internal testing

**Exit criteria:** working Khmer suggestions typing into TikTok/YouTube on your own Android phone.

### Phase 3 — iOS Keyboard Extension (Swift)
- [ ] 3.1 Xcode Custom Keyboard Extension target
- [ ] 3.2 Port lookup logic to Swift (reuse Phase 1 JSON)
- [ ] 3.3 Basic QWERTY layout
- [ ] 3.4 Suggestion bar UI
- [ ] 3.5 Implement/test "Allow Full Access" flow
- [ ] 3.6 Test in real target apps
- [ ] 3.7 Prepare for App Store submission

**Exit criteria:** same working experience as Android, on iPhone.

### Phase 4 — Browser Extension
- [ ] 4.1 Manifest V3 Chrome extension project
- [ ] 4.2 Detect editable fields (`input`, `textarea`, `contenteditable`)
- [ ] 4.3 Reuse reverse-index + fuzzy matching logic in JavaScript
- [ ] 4.4 Suggestion popup anchored to cursor
- [ ] 4.5 Insert selected Khmer text into field
- [ ] 4.6 Test across target sites
- [ ] 4.7 Package/submit to Chrome Web Store

### Phase 5 — Data & Feedback Loop (ongoing once live)
- [ ] 5.1 Log corrections (user picks a non-top-ranked suggestion)
- [ ] 5.2 Decide collection method (local-only vs. opt-in backend) — privacy-conscious default
- [ ] 5.3 Periodically re-weight `phonetic_rules`/`reverse_index` from logged corrections
- [ ] 5.4 Expand vocabulary toward general Khmer using khmerlbdict once slang coverage is solid

---

## Current Position

**Phase 1, step 1.1 — done.** Python project scaffold is in place: `src/sing_khmer_engine/` package, `tests/` (pytest, smoke test passing), `data/` for future vocabulary/rules, venv + `requirements.txt`/`requirements-dev.txt` for dependencies, `pyproject.toml` for pytest config, `.gitignore`, and `README.md`. Local-only git repo for now (no remote yet).

**Phase 1, step 1.2 — format + tooling in place; curation pending.** The vocabulary data
format is set up as `data/vocabulary.csv` (columns: `khmer, meaning, frequency, is_slang,
romanizations, notes`; frequency is a rough 1–5 scale; `romanizations` holds the space-separated
Sing Khmer/Latin spellings), documented in `data/README.md`. A validating loader lives at
`src/sing_khmer_engine/vocabulary.py` (`VocabEntry` dataclass + `load()`), with tests in
`tests/test_vocabulary.py`. The file currently holds **15 seed example rows to verify/replace** —
the remaining 1.2 work is for the native speaker to curate the full ~100–200 casual/chat words.
The `[ ] 1.2` box stays unchecked until that curation is done.

**Phase 1, step 1.3 — done.** KCC segmenter implemented at `src/sing_khmer_engine/kcc.py`
(`segment(text) -> list[str]`, a dependency-free Unicode rule), with tests in
`tests/test_kcc.py` and a demo at `scripts/show_kccs.py` that prints each vocabulary word's KCC
breakdown. Segmentation is computed from the Khmer script, so it runs unchanged on the full team
word list once step 1.2 curation is complete. Verified on the 15 seed words (e.g. `ចឹង → ចឹ · ង`,
`ស្អាត → ស្អា · ត`).

**Phase 1, step 1.2 — DONE.** The team curated **257 words** in the Excel sheet
(`data/sing-khmer-vocab-collection.xlsx`); merged into `data/vocabulary.csv` (spellings normalized:
split on comma/space, lowercased, deduped). `meaning` is now optional in the loader (the team
dropped it). 257 entries load and validate.

**Phase 1, step 1.4 — first pass done (exact rules only).** `src/sing_khmer_engine/phonetic_rules.py`
(`build_rules()` + `Rule` dataclass + `coverage()`) derives KCC→spelling rules with confidence
weights. Two sources: **direct** (single-KCC words = unambiguous ground truth) and **aligned**
(two-KCC anchored subtraction). Only **direct** ships by default — `include_aligned` is off because
the aligned heuristic misattributes spellings (e.g. guessed `ក`→`ok`). Output saved by
`scripts/build_phonetic_rules.py` to `data/phonetic_rules.csv` (49/264 KCCs covered exactly) plus
`data/phonetic_rules_review.csv` (the other 215, with example words). Tests in
`tests/test_phonetic_rules.py`.

**KEY FINDING (affects design):** most collected Sing Khmer spellings are **whole-word
abbreviations**, not compositional syllable spellings — e.g. `ខ្ញុំ→nh`, `ចង់→jg`, `នឹង→ng`,
`ហើយ→hz/hx/hy`. These cannot be split into per-KCC pieces. Consequence: the **reverse index (1.6)
should be built primarily from the collected word→romanization data (ground truth)**, which is
100% accurate for every collected spelling; per-KCC `phonetic_rules` are a *secondary
generalization layer* for unseen input, not the primary lookup source. This revises the CLAUDE.md
"three-part data model" emphasis.

**Phase 1, steps 1.6 & 1.7 — DONE. The converter works.** `reverse_index.py` (`build_index()` +
`Candidate`) builds the Latin→Khmer lookup table from collected romanizations (backbone) plus a
generated layer from phonetic rules; `lookup.py` (`Engine` + `convert()`) does exact-match ranked
lookup. Interactive demo: `PYTHONPATH=src python scripts/convert.py` (or pass words as args).
Verified: `jg → ចង់(5), ចឹង(4)` (homophones ranked by frequency — the exact ambiguity the user
flagged), `nh → ខ្ញុំ`, `sl → ស្រឡាញ់`, `ss → សង្សារ`; unknown input returns empty. 353 spellings
indexed. Tests in `tests/test_reverse_index.py`, `tests/test_lookup.py`.

**Sentence support + web demo added.** `Engine.convert_sentence()` / `convert_sentence_text()`
split input on spaces, convert each word (keeping candidates + punctuation, unknown words fall
through): `nh sl bong → ខ្ញុំ ស្រឡាញ់ បង`. No-space segmentation is a later refinement.
`scripts/build_web_demo.py` writes a self-contained `web/index.html` (offline; embeds the index)
so Khmer renders correctly in a browser (terminals can't shape Khmer — that's a display limit, not
a data bug) with clickable per-word alternatives. 43 tests total.

**Next up: step 1.8** — fuzzy/edit-distance fallback for input with no exact match (e.g. typos).
Then 1.9 (measure accuracy on real chat) and 1.5 (seed uncovered KCCs from IDRI-LAB's romanizer to
widen the generated layer).

**Reminders:** team's disambiguation notes captured in `data/vocabulary.csv` (e.g. `jg` = ចង់ vs
ចឹង by sentence position → needs the user-selection UX in 1.7). Project is still **local-only**
(no git remote yet) — recommend pushing to GitHub before more work accrues.
