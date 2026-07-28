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
- **Code-switching (deferred):** users mix English and Sing Khmer in one message (e.g. `u` for
  "you", English words dropped mid-sentence). The engine currently converts every token and passes
  unknown tokens through unchanged — good enough for now. Deliberately IGNORED for the current
  phase; revisit later (needs a way to detect "leave this English word alone" vs "convert it").

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
- [x] 1.8 Fuzzy/edit-distance fallback for non-exact matches
- [ ] 1.9 Test against real romanized chat examples, measure accuracy
- [ ] 1.10 Iterate on rules/weights based on failures

**Exit criteria:** correct Khmer word lands in the top 3 candidates for most test examples.

### Phase 2 — Android Keyboard Shell (Kotlin) — DETAILED PLAN

**Key architectural decision:** don't port the Python generation logic (KCC segmentation +
phonetic-rules combination) to Kotlin. It's deterministic and needs no per-keystroke computation,
so it runs once, offline, in Python (already built in Phase 1) and is **exported to a static JSON
asset** (`reverse_index.json`: `spelling -> [[khmer, score, source], ...]`) that ships inside the
Android app. Kotlin only needs to: (a) look up a key in that JSON (trivial `Map` access), and
(b) implement edit-distance fuzzy fallback for keys with no exact match (the one piece that
genuinely depends on live user input, so it must run on-device — port `fuzzy.py`'s `levenshtein`,
~15 lines of Kotlin). This mirrors what the web app already does for the browser
demo — Android is the same pattern, native.

**UX model (decided from Phase 1 testing):** behaves like iOS Text Replacement (auto-converts
inline as you type) but with a suggestion strip for ambiguous words, because — unlike iOS Text
Replacement's fixed 1:1 shortcuts — one Sing Khmer spelling often maps to *several* Khmer words
(homophones, e.g. `jg` → ចង់ or ចឹង). So: convert the current word automatically the moment a
space/punctuation is typed (top-ranked candidate), but keep it "live" in the suggestion strip so
one tap swaps it for an alternative — same interaction Google Input Tools / Gboard use for CJK.

**Steps:**
- [ ] 2.0 Export step: `scripts/export_index.py` — dump `Engine().index` to
      `android/app/src/main/assets/reverse_index.json`. Re-run whenever `vocabulary.csv` changes;
      no other Phase 1 code needs porting.
- [ ] 2.1 Minimal `InputMethodService` project in Android Studio (empty keyboard that just shows)
- [ ] 2.2 Study/fork an open-source keyboard (e.g. Simple Keyboard / OpenBoard) as reference for
      the `InputMethodService` + key-rendering boilerplate — don't build a keyboard renderer from
      scratch
- [ ] 2.3 Basic QWERTY layout outputting raw Latin text first (prove key events + text commit work)
- [ ] 2.4 Load `reverse_index.json` as a `Map<String, List<Candidate>>` at IME startup; implement
      Kotlin `levenshtein`/`within` for the fuzzy fallback (direct port of `fuzzy.py`)
- [ ] 2.5 Composing-word buffer: track the current word being typed (like IME "composing text");
      on space/punctuation/enter, look up the buffer and auto-commit the top candidate (the
      "Text-Replacement-style" behavior above)
- [ ] 2.6 Suggestion strip UI above the keyboard showing ranked candidates for the
      just-committed (or currently composing) word; tapping an alternative swaps the committed
      text via `InputConnection.setComposingText`/`commitText`
- [ ] 2.7 Backspace handling: deleting into a just-converted word should be able to revert to the
      original Latin (or cycle candidates) rather than deleting Khmer character-by-character blindly
- [ ] 2.8 Test in real target apps (TikTok, YouTube comments, Messenger, Telegram)
- [ ] 2.9 Distribute for personal/internal testing (direct APK sideload first; Firebase App
      Distribution if the team testing it grows beyond a couple of phones)

**Carried over from Phase 1 findings (don't re-litigate in Phase 2):**
- Ranking is (collected > generated > fuzzy) then by frequency — same order Android should render
  candidates in.
- Homophone disambiguation (e.g. `jg`) has no fixed rule yet (position-in-sentence idea flagged by
  the team is unimplemented) — Phase 2 can initially just rank by frequency and let the user tap to
  correct, same as Phase 1's web demo.
- No-space segmentation (typing a whole sentence with no spaces) is still unsolved — Android phase
  can assume space-delimited input same as the Phase 1 prototype; this remains a known gap.

**Exit criteria:** working Khmer suggestions typing into TikTok/YouTube on your own Android phone,
with tap-to-correct working for at least the known homophone cases.

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

**Vocabulary last merged:** user's V2 Excel (`singkhmervocabcollectionV2.xlsx`, 383 words with
retuned frequencies) merged in — Excel is authoritative for anything it covers; the 43
AI-researched extras not in the Excel were preserved, and romanizations were UNIONed for overlaps
(so e.g. `បង` kept both `bong` and the added `b`). **426 words total.** For the next Excel update,
reuse the same merge approach (`/tmp` scratch script pattern): Excel wins on freq/slang, union
romanizations, keep current-only words, preserve `notes` like the `jg` ចង់-vs-ចឹង guidance.

**Engine accuracy is under active improvement** (see the engine-improvement plan): the user found
many words/spellings aren't recognized. Diagnosis: 55% of the 258 words have only ONE collected
spelling, and only 49/264 KCCs have exact phonetic rules, so real typing variation often misses.
Plan (in order): (0) build a diagnostics tool to see exactly why a word misses, (1) add a phonetic
normalization layer (collapse doubled letters, drop optional trailing `h`, unify interchangeable
letter clusters — rules derived from real variant pairs already in the data), (2) smarter/wider
fuzzy matching, (3) widen phonetic-rules coverage (revives deferred step 1.5). Vocabulary growth
continues in parallel (both the user's additions and my own research, see below).

**Phase 1 (Python prototype): steps 1.1–1.4, 1.6–1.8 DONE. 1.9 explicitly SKIPPED for now
(picking up again later — see below). Moving into Phase 2 planning.**

Summary of what's built (all in `sing-khmer-engine-2` repo, `src/sing_khmer_engine/`):
- **1.1 Scaffold** — `src/`-layout package, venv + `requirements*.txt`, pytest via `pyproject.toml`.
- **1.2 Vocabulary — DONE, still growing.** **474 words** in `data/vocabulary.csv`
  (columns: `khmer, meaning, frequency, is_slang, romanizations, notes`; `meaning` optional/unused).
  **romanizations format = alternatives separated by SPACES **or** COMMAS (both work, matches how
  the native speaker actually types); a genuine multi-word spelling uses `+` (e.g. `msel+minh` for
  ម្សិលមិញ).** Parsed by `vocabulary.parse_romanizations()` (split on `[,\s]+`, then `+`→space).
  History: format churned space→comma→(space|comma, `+`=multiword) because the developer kept using
  spaces for alternatives out of habit; the current format respects that. The 45 genuine multi-word
  spellings (from the Excel) were auto-migrated to `+`; 5 accidental space-alternatives
  (`bongrean prean`, `kompong pong`, `pkert bongkert`, `kroub krob`, `phg pg`) were split back.
  Loader + validation: `vocabulary.py` (`VocabEntry`, `load()`). Team-curated core + AI-researched
  additions (latter tagged `(AI-suggested — verify)` in `notes`). Anyone edits rows directly in the
  CSV — no Excel needed. **When adding: use commas between spellings**, spaces only inside one
  multi-word spelling. (Docs: `data/README.md`.)
- **1.3 KCC segmentation — DONE.** `kcc.py` (`segment()`), a dependency-free Unicode rule splitting
  Khmer text into syllable clusters. Demo: `scripts/show_kccs.py`.
- **1.4 Phonetic rules — SUPERSEDED (file deleted).** The romanizer (`romanizer.py`) replaced this
  entirely; kept here as history. `phonetic_rules.py` (`build_rules()`) derived KCC→
  spelling rules from **direct** evidence only (single-KCC words = unambiguous ground truth); the
  **aligned** heuristic (two-KCC anchored subtraction) exists but is off by default — it
  misattributes spellings. 49/264 KCCs covered exactly (`data/phonetic_rules.csv`); the rest are
  logged in `data/phonetic_rules_review.csv` for later.
  **KEY FINDING:** most collected Sing Khmer spellings are **whole-word abbreviations**, not
  compositional syllable spellings (`ខ្ញុំ→nh`, `ចង់→jg`, `នឹង→ng`). So the reverse index is built
  primarily from **collected** word→romanization data (ground truth, 100% accurate); per-KCC rules
  are a secondary *generalization* layer for words/spellings nobody typed — this revises the
  original "three-part data model" emphasis.
- **1.6 & 1.7 Reverse index + lookup — DONE. Converter works end-to-end.** `reverse_index.py`
  (`build_index()`) + `lookup.py` (`Engine.convert()`), ranked by (collected > generated > fuzzy)
  then frequency. Homophones return ranked options (`jg → ចង់(5), ចឹង(4)`).
- **1.8 Fuzzy matching — DONE.** `fuzzy.py` (Levenshtein edit distance); typos fall back to the
  closest known spelling (`srolan → ស្រឡាញ់`).
- **Segmentation decoder — DONE (fixes two user-reported bugs).** `Engine.decode()` (in `lookup.py`,
  a Viterbi-style DP over the reverse index, `_segment_spans`) replaced the old naive space-split.
  It covers a whole message with the best sequence of known spellings, so it works **WITH OR WITHOUT
  spaces** (`nhslbong → ខ្ញុំ ស្រឡាញ់ បង`) and matches **multi-word spellings** as one unit
  (`msel minh → ម្សិលមិញ`). Unknown/leftover tokens are fuzzy-matched, then passed through. Single-char
  spellings (`b`, `s`) only match as whole space-delimited tokens so they don't chop longer runs.
  `convert_sentence*` now delegate to `decode`. Known remaining gap: a multi-word spelling typed with
  NO internal space (`mselminh`) isn't matched; and no-space + typo together is weak.
  - This fixed: (bug 1) "had to use spaces" — now optional; (bug 2) `minh` wrongly → ម្សិលមិញ, caused
    by the earlier merge splitting the multi-word spelling `msel minh` on the space. Fixed by the
    comma format (above) so `msel minh` is one spelling and `minh` is free.
- **Compound words + alternative readings — DONE (fixes 3rd user bug).** The decoder is now k-best
  (`_segment_kbest`) with a per-word cost (`_WORD_COST`) so a whole compound word beats splitting it:
  `bongrean → បង្រៀន` (was wrongly `បង រៀន`). `Engine.readings(text, k)` returns the top distinct
  whole-message readings so the UI can let the user **switch** between the compound and the split
  (`bongrean → [បង្រៀន, បង រៀន]`). The web app shows these as a clickable "readings" row.
  **DATA DEPENDENCY:** compound/multi-KCC words must be IN `vocabulary.csv` (e.g. `បង្រៀន,,4,false,
  bongrean,`) — the developer should keep adding these ("connect the KCCs"). The engine can only
  offer a compound it knows. `bong rean` typed WITH a space still splits unless បង្រៀន also has the
  multi-word spelling `bong rean` — worth adding both spellings for common compounds.
- **How to test (preferred): the web app** — `PYTHONPATH=src uvicorn api.index:app --reload`, then
  open http://localhost:8000. It uses the REAL engine (no duplicated decoder), and needs no database
  locally — it falls back to SQLite. Khmer renders correctly because it's a browser (terminals can't
  shape Khmer — a display limit, not a data bug). See `docs/DEPLOY.md`.
  NOTE: `scripts/serve.py` and `scripts/build_web_demo.py` + `web/` were DELETED — each carried a
  hand-synced JavaScript copy of the decoder. The web app replaces both.
- **`scripts/diagnose.py`** — explains WHY input did/didn't convert: EXACT vs FUZZY (with distance)
  vs NO MATCH (shows nearest known spelling + raw edit distance, ignoring the threshold), so
  "missing word" is distinguishable from "spelling too far off". Backed by `Engine.diagnose()` /
  `Diagnosis` in `lookup.py`. Use this to find real coverage gaps before adding words/rules.
- Other demos: `scripts/convert.py` (terminal, word or sentence).
- **UX decision (carries into Phase 2):** behaves like iOS Text Replacement (auto-converts inline)
  but with a tap-to-swap suggestion strip for homophones, since Sing Khmer spellings are ambiguous
  in a way fixed iOS shortcuts aren't. See Phase 2 plan above for how this becomes the Android IME.
- 49 tests passing throughout (`pytest`).

**1.9 (measure accuracy on real chat examples) — SKIPPED FOR NOW.** Revisit once there's a larger
corpus of real chat messages to test against and/or once Phase 2 gives a reason to prioritize
accuracy tuning again. Still on the roadmap, just not being worked on currently.

**Deferred:** 1.5 (skim IDRI-LAB's romanizer to seed the 215 uncovered KCCs) and 1.10 (tune
weights) — pick up alongside or after 1.9.

**Next up: Phase 2 (Android keyboard shell)** — see the detailed step-by-step plan above
(2.0–2.9). Starting point: `scripts/export_index.py` (not yet written) to dump the reverse index
to `reverse_index.json` for the Android app to bundle.

**Environment note:** development has moved between a cloud session and the developer's local Mac
(VS Code, cloned from `github.com/SrunLyheang/sing-khmer-engine-2`). The two only sync via
git push/pull — there is no direct file access between them. If picking this project up in a new
session, check `git log`/`git status` first to see which side has the latest work before editing.

**Next up: step 1.8** — fuzzy/edit-distance fallback for input with no exact match (e.g. typos).
Then 1.9 (measure accuracy on real chat) and 1.5 (seed uncovered KCCs from IDRI-LAB's romanizer to
widen the generated layer).

**Reminders:** team's disambiguation notes captured in `data/vocabulary.csv` (e.g. `jg` = ចង់ vs
ចឹង by sentence position → needs the user-selection UX in 1.7). Project is still **local-only**
(no git remote yet) — recommend pushing to GitHub before more work accrues.
