# Sing Khmer Engine — A Plain-English Guide

This guide explains **how the code is organized and how to run it** — written for someone who
understands the *goal* but wants to understand the *codebase*. For how the conversion itself
works conceptually, see [EXPLAINER.md](EXPLAINER.md) first; this file is the map of the files.

---

## 1. What this project does (the 10-second version)

People type Khmer using English letters — "sing khmer" — like `nh` instead of `ខ្ញុំ` ("I").
This project converts that romanized typing back into real Khmer script and suggests the right
word. The **engine** (pure Python, no dependencies) does the conversion; a small **web app**
wraps it so people can actually use it and so real usage teaches the dictionary new words.

> **You type:** `nhslbong`  →  **the engine suggests:** `ខ្ញុំស្រឡាញ់បង`

---

## 2. The files, one by one

```text
sing-khmer-engine/
│
├── data/                        ← THE DATA
│   ├── vocabulary.csv           ← the master word list (1,244 words and growing)
│   └── english_words.txt        ← common English words, so code-switched words
│                                   ("ok", "message") aren't forced into Khmer
│
├── src/sing_khmer_engine/       ← THE ENGINE (pure standard library, no deps)
│   ├── vocabulary.py            ← reads & validates data/vocabulary.csv
│   ├── kcc.py                   ← breaks a Khmer word into syllable clusters (KCCs)
│   ├── romanizer.py             ← generates plausible Latin spellings for a Khmer word
│   ├── reverse_index.py         ← builds the spelling -> Khmer-word lookup table
│   ├── fuzzy.py                 ← edit-distance matching for typos / near-misses
│   ├── english.py               ← common-English-word detection (code-switching)
│   └── lookup.py                ← `Engine`: ties everything together — convert a
│                                   spelling, or decode a whole message
│
├── api/                         ← THE WEB APP (needs api/, requirements.txt)
│   ├── index.py                 ← FastAPI routes: convert/record/feedback, static
│                                   pages, health check, CSV export
│   ├── accounts.py              ← reviewer accounts: passwords, signed-cookie sessions
│   ├── admin_routes.py          ← review-queue API + GitHub pull-request submission
│   ├── security.py              ← sessions, rate limiting, input validation
│   ├── filters.py                ← quality-scores a submitted spelling/word before storing
│   └── storage.py               ← SQLite (local) / Postgres (deployed) data layer
│
├── webui/                       ← THE FRONTEND (static, no build step)
│   ├── index.html, app.js       ← the converter page
│   ├── admin.html, admin.js     ← the reviewer dashboard (`/review`)
│   ├── i18n.js                  ← English/Khmer UI text switching
│   └── styles.css               ← styling for the converter page
│
├── tests/                       ← AUTOMATIC CHECKS (pytest)
│
├── scripts/                     ← CLIs you run directly, see below
│
├── GUIDE.md                     ← this file
├── EXPLAINER.md                 ← how conversion works, explained simply
├── README.md                    ← short project intro
├── CLAUDE.md                    ← the project memory / roadmap / decisions
├── requirements.txt             ← web app's runtime dependencies
├── requirements-dev.txt         ← dev/test dependencies
└── pytest.ini                   ← settings so pytest can find the code
```

**The mental model:** `data/` is the dictionary, `src/` is the engine that reads it, `api/` +
`webui/` are the app that puts it in front of people, and `scripts/` are the tools you run by
hand to grow and check the dictionary.

---

## 3. The engine, in one paragraph each

- **`vocabulary.py`** — reads `data/vocabulary.csv`. Each row becomes a `VocabEntry` (Khmer word,
  frequency 1–5, whether it's slang, its known Latin spellings). Bad rows are rejected loudly
  with the row number, so bad data can't silently poison the engine.
- **`kcc.py`** — splits Khmer text into **KCCs** (Khmer Character Clusters), the syllable-like
  unit Khmer must be handled in (a vowel sign can never stand alone; it attaches to a consonant).
- **`romanizer.py`** — given a Khmer word, generates plausible Latin spellings, so a reasonable
  spelling nobody has typed yet can still be found (scored lower than spellings people actually
  used).
- **`reverse_index.py`** — combines every word's collected + generated spellings into one big
  `spelling -> [Khmer candidates]` map. This is the actual runtime lookup table.
- **`fuzzy.py`** — bounded Levenshtein edit distance, for typos that don't match anything exactly.
- **`english.py`** — a bundled common-English wordlist, so `ok`/`message`/`computer` can be left
  as English instead of forced into a Khmer guess.
- **`lookup.py`** — the `Engine` class. Loads everything above once, then answers:
  - `convert(spelling)` — ranked Khmer candidates for one spelling.
  - `decode(text)` — a whole message, with or without spaces, split into matched/unmatched
    pieces (this is what the web app actually calls).
  - `diagnose(spelling)` — explains *why* a spelling did or didn't match (exact / fuzzy / nothing
    close) — the tool of first resort when a word "should" convert but doesn't.

```python
from sing_khmer_engine.lookup import Engine

eng = Engine()
eng.convert("jg")              # -> [ចង់ (score 5), ចឹង (score 4)]  (homophones, ranked)
eng.convert_sentence_text("nhslbong")   # -> "ខ្ញុំស្រឡាញ់បង"
```

---

## 4. The web app, in one paragraph each

- **`api/index.py`** — the FastAPI app. Serves the converter page and its static assets, and the
  three endpoints the page calls: `/api/convert` (get suggestions), `/api/record` (log what
  actually happened after a conversion settles), `/api/feedback` (an explicit correction). Also
  serves `/api/health` and the CSV export route.
- **`api/accounts.py`** — reviewer accounts: scrypt-hashed passwords, signed session cookies,
  invite links. The first account created (via `ADMIN_TOKEN`) becomes the **owner**; everyone
  else is a **reviewer**.
- **`api/admin_routes.py`** — everything behind `/review`: the correction queue, accept/reject/
  undo, and — owner only — pushing accepted corrections to GitHub as a pull request against
  `data/vocabulary.csv`.
- **`api/security.py`** — session signing, per-endpoint rate limiting, and input scrubbing
  (emails/links/long digit runs stripped before anything is stored).
- **`api/filters.py`** — scores an incoming spelling/word so obvious junk sorts to the bottom of
  the review queue instead of being silently discarded (a rejected word is still evidence).
- **`api/storage.py`** — SQLite locally, Postgres (Neon) when deployed; one thin layer so the
  rest of the app doesn't care which.

None of this affects the engine itself — `src/sing_khmer_engine/` has zero dependency on `api/`.

---

## 5. The scripts you'll actually run

| Script | What it's for |
| --- | --- |
| `scripts/convert.py` | Convert one word or a whole sentence from the terminal. |
| `scripts/diagnose.py` | Explain why a spelling did/didn't convert (exact/fuzzy/no match). |
| `scripts/show_kccs.py` | See how vocabulary words break into syllable clusters. |
| `scripts/romanize.py` | Explore the auto-generated spellings for a Khmer word. |
| `scripts/check_vocab.py` | Lint `data/vocabulary.csv` for bad characters, duplicates, mixed-up spellings. |
| `scripts/recall.py` | Measure how much of the vocabulary the engine can still find (QA metric). |
| `scripts/pick_words.py` | Scan a frequency wordlist for common words not yet in the DB, with predicted spellings. |
| `scripts/pick_compounds.py` | Same idea, for compound words that split into words you already have. |
| `scripts/backup_db.py` | Dump every database table to timestamped JSON. |
| `scripts/export_feedback.py` | Export what users typed/corrected as a formatted `.xlsx` for review. |
| `scripts/show_feedback.py` | Same data as above, printed straight to the terminal. |
| `scripts/purge.py` | Delete raw user text past the 90-day retention window (run on a schedule). |

---

## 6. How to run it yourself

```bash
# 1. Set up
python3 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# 2. Run all the automatic checks
pytest
#    -> "123 passed"

# 3. Try the engine directly
PYTHONPATH=src python scripts/convert.py "nhslbong"

# 4. Or run the actual web app
pip install -r requirements.txt
PYTHONPATH=src uvicorn api.index:app --reload
#    -> open http://localhost:8000
```

If `pytest` passes, the engine is healthy. If you add words to `data/vocabulary.csv`, run
`scripts/check_vocab.py` and `pytest` again — both re-check your new data.

---

## 7. How you and the code work together

| You do… | The code does… |
| --- | --- |
| Add real Khmer words + Sing Khmer spellings to `data/vocabulary.csv` | Validate the list, break words into syllables, generate extra spellings, build the lookup table |
| Review words people typed at `/review` | Rank the evidence so your review time goes to the words that matter most |
| Decide what reaches the dictionary (owner only) | Open the GitHub pull request for you once you approve |

**You are the language expert. The code is the tireless assistant.**

---

## 8. Mini-glossary

- **Sing Khmer / romanization** — writing Khmer with English letters (`nh` for `ខ្ញុំ`).
- **KCC (Khmer Character Cluster)** — one syllable block of Khmer; the unit the engine works on.
- **Reverse index** — the big lookup table: every known spelling → its Khmer word(s) + score.
- **Fuzzy match** — when nothing matches exactly, the closest known spelling by edit distance.
- **Review queue** — words/corrections people submitted, waiting for a human to accept or reject.
- **pytest** — the tool that runs the automatic checks.
- **venv** — a private, per-project workspace for Python libraries.
