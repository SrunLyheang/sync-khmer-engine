# Sing Khmer Engine — A Plain-English Guide

This guide explains **what the project is, how the code works, and how to run it yourself** —
written for someone who understands the *goal* but wants to understand the *code*. No prior Python
experience assumed.

---

## 1. What this project does (the 10-second version)

People type Khmer using English letters — "sing khmer" — like `jueng` instead of `ចឹង`.
This project is the **brain** that turns those English-letter spellings back into real Khmer script,
and suggests the right word. Right now we are building that brain in Python, on a computer, before
it ever becomes a phone keyboard.

> **You type:** `jueng`  →  **the engine suggests:** `ចឹង`

---

## 2. The big idea: how conversion will work

Think of it like a **translator with a phrasebook**. To translate `jueng` → `ចឹង`, the engine needs
a phrasebook that says "when someone types `jueng`, they probably mean `ចឹង`." We don't write that
phrasebook by hand for every possible spelling — that would be impossible. Instead we build it in
small, logical pieces:

```
   ┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐     ┌──────────────┐
   │ 1. WORD LIST    │     │ 2. BREAK INTO    │     │ 3. SPELLING RULES │     │ 4. BIG LOOKUP│
   │ (vocabulary)    │ ──▶ │    SYLLABLES     │ ──▶ │  (each syllable → │ ──▶ │    TABLE     │
   │ ចឹង, ស្អាត, ...   │     │   (KCCs)         │     │  English letters) │     │ jueng → ចឹង   │
   └─────────────────┘     └──────────────────┘     └───────────────────┘     └──────────────┘
        step 1.2                 step 1.3                  step 1.4                 step 1.6
      ✅ (your team)             ✅ DONE                  ⬅ next                   coming

                                                                          ┌──────────────────┐
                                                                          │ 5. LOOKUP + RANK │
                                                             you type ──▶ │  jueng → ចឹង #1   │
                                                                          │         ចីង  #2   │
                                                                          └──────────────────┘
                                                                                step 1.7
```

The key insight: we break each word into **syllables** (called KCCs), figure out the English-letter
spellings for each *syllable*, and then the computer automatically combines them to generate every
possible full-word spelling. That auto-generated list becomes the lookup table.

---

## 3. The files, one by one

Here's every important file and what it's for. You don't need to touch most of them.

```
sing-khmer-engine/
│
├── data/                        ← THE DATA (this is mostly YOUR part)
│   ├── vocabulary.csv           ← the master word list the engine reads
│   ├── sing-khmer-vocab-        ← the Excel sheet your team fills in
│   │   collection.xlsx
│   └── README.md                ← explains the columns in vocabulary.csv
│
├── src/sing_khmer_engine/       ← THE CODE (my part — the "brain")
│   ├── vocabulary.py            ← reads & checks the word list
│   ├── kcc.py                   ← breaks a Khmer word into syllables
│   └── __init__.py              ← marks this folder as the code package
│
├── tests/                       ← AUTOMATIC CHECKS (prove the code works)
│   ├── test_vocabulary.py
│   ├── test_kcc.py
│   └── test_smoke.py
│
├── scripts/
│   └── show_kccs.py             ← a demo you can run to SEE it working
│
├── GUIDE.md                     ← this file
├── README.md                    ← short project intro
├── CLAUDE.md                    ← the project memory / roadmap / decisions
├── requirements.txt             ← list of code libraries needed (empty for now)
├── requirements-dev.txt         ← libraries needed for testing (pytest)
└── pyproject.toml               ← settings so the tests can find the code
```

**The mental model:** `data/` is the ingredients, `src/` is the recipe, `tests/` makes sure the
recipe didn't break, and `scripts/` lets you taste the result.

---

## 4. How the code works right now

Two pieces of the brain are built. Here's what each does, with real examples.

### Piece A — `vocabulary.py`: reading the word list

The word list lives in a spreadsheet file (`data/vocabulary.csv`). This code opens that file, reads
each row, and **checks it for mistakes** (bad numbers, duplicate words, missing fields). It hands
back a clean list the rest of the engine can trust.

Each word becomes a `VocabEntry` — think of it as an index card with these fields:

| Field           | Example          | Meaning                                   |
|-----------------|------------------|-------------------------------------------|
| `khmer`         | `ចឹង`             | the word in Khmer script                  |
| `meaning`       | `like that / so` | English meaning                           |
| `frequency`     | `4`              | how common (1–5)                          |
| `is_slang`      | `True`           | casual chat slang?                        |
| `romanizations` | `('jueng','jg')` | the Sing Khmer spellings (your team's job)|

The one command that matters:

```python
from sing_khmer_engine.vocabulary import load
words = load()          # reads data/vocabulary.csv, returns the list of cards
print(len(words))       # -> how many words
print(words[0].khmer)   # -> សួស្តី
```

If a row in the spreadsheet is broken (say, frequency is `9` instead of 1–5), `load()` **refuses and
tells you the exact row number**. That's on purpose — it stops bad data from silently poisoning the
engine.

### Piece B — `kcc.py`: breaking a word into syllables

This is the heart of step 1.3. Khmer isn't written letter-by-letter like English — letters stack and
combine into syllable blocks. You can't split them naively. This code knows the Khmer Unicode rules
and splits correctly.

```python
from sing_khmer_engine.kcc import segment
segment("ចឹង")     # -> ['ចឹ', 'ង']       (two syllables)
segment("ស្អាត")   # -> ['ស្អា', 'ត']      (keeps the stacked ្អ together!)
segment("ខ្ញុំ")    # -> ['ខ្ញុំ']          (all one syllable)
```

**Why this matters:** the next step (spelling rules) works on these syllables, not whole words. Once
we know how each *syllable* can be typed in English letters, the computer combines them to cover the
whole word automatically.

---

## 5. How to run it yourself (step by step)

You need **Python** installed (version 3.11 or newer). Then open a terminal **inside the project
folder** and run these once to set up:

```bash
# 1. Create a private workspace for this project's libraries
python3 -m venv .venv

# 2. Turn that workspace on
source .venv/bin/activate         # Mac/Linux
#    .venv\Scripts\activate       # Windows

# 3. Install the testing tool
pip install -r requirements-dev.txt
```

Now the two things worth running:

```bash
# A) Run all the automatic checks — proves everything works
pytest
#    -> you should see something like "26 passed"

# B) See the syllable-splitter in action on the current words
PYTHONPATH=src python scripts/show_kccs.py
#    -> prints  ចឹង → ចឹ · ង   etc.
```

That's it. If `pytest` says "passed," the brain is healthy. If you add words to the spreadsheet and
run `pytest` again, it re-checks your new data too.

---

## 6. How you and the code work together

Here's the division of labor, so it's clear what's *yours* and what's *mine (the code's)*:

| You (and your team) do…                          | The code does…                                    |
|--------------------------------------------------|---------------------------------------------------|
| Fill in real Khmer words + Sing Khmer spellings  | Read & validate the list (`vocabulary.py`)        |
| in the spreadsheet                               | Break each word into syllables (`kcc.py`)         |
| Decide what counts as good slang                 | (next) Turn syllables into spelling rules         |
| Test it with real chat examples later            | (next) Build the lookup table & rank suggestions  |

**You are the language expert. The code is the tireless assistant.** You provide the Khmer knowledge;
the code does the repetitive combining, checking, and looking-up.

---

## 7. What's built vs. what's coming

| Step | What it is                                         | Status                         |
|------|----------------------------------------------------|--------------------------------|
| 1.1  | Set up the project                                 | ✅ done                        |
| 1.2  | Collect ~100–200 words + spellings                 | ⏳ your team (the Excel sheet) |
| 1.3  | Break words into syllables (KCCs)                  | ✅ done                        |
| 1.4  | Spelling rules: each syllable → English letters    | ⬅ next (needs your spellings)  |
| 1.6  | Auto-build the big lookup table                    | coming                         |
| 1.7  | Type Sing Khmer → get ranked Khmer suggestions     | coming — **first "wow" moment**|
| 1.8+ | Handle typos, test accuracy, tune                  | coming                         |

**The goal:** you type `jueng`, and `ចឹង` shows up in the top 3 suggestions.

---

## 8. Mini-glossary

- **Sing Khmer / romanization** — writing Khmer with English letters (`jueng` for `ចឹង`).
- **KCC (Khmer Character Cluster)** — one syllable block of Khmer; the unit the engine works on.
- **Vocabulary** — the master list of words the engine knows.
- **Phonetic rules** — the "each syllable can be typed these ways" table (step 1.4).
- **Reverse index** — the big auto-generated lookup table: every spelling → its Khmer word.
- **pytest** — the tool that runs the automatic checks.
- **venv** — a private, per-project workspace for Python libraries so projects don't clash.

---

*Questions to ask next time: "show me word X broken into syllables," "add these words to the list,"
or "start step 1.4." You don't need to memorize any of this — just come back to this file.*
