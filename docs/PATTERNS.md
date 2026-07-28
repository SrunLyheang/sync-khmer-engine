# The Sing Khmer romanization pattern (learned from your data)

People can read each other's Sing Khmer even when they spell it differently because the
spelling follows a **pattern** — it's *phonetic* (how the word sounds), not a copy of the
Khmer letters. This document is that pattern, extracted from `data/vocabulary.csv`, and it's
what `scripts/romanize.py` uses to predict spellings for new words.

## How a word is spelled, syllable by syllable

Khmer is written in **syllable clusters** (KCCs). Each cluster becomes
`onset consonant(s)` + `vowel` + (if it's a final consonant) a `reduced ending`. Three rules,
applied per cluster:

### 1. Final consonants are *reduced*
A consonant at the very end of a word is spoken unreleased, so it's typed short — and
final **រ is usually dropped** because it's silent:

| final | typed |   | final | typed |   | final | typed |
|------|-------|---|------|-------|---|------|-------|
| ក ខ គ | k | | ង | ng | | ច ជ | ch |
| ញ | nh | | ដ ត ថ ទ ធ | t | | ន ណ | n |
| ប ព ភ | p | | ម | m | | យ | y |
| រ | *(dropped)* | | ល | l | | វ | v |
| ស | s | | ហ · ◌ះ | h | | | |

Examples: អ្នក → **nek** (final ក), ចាស → **jah** (final ស→h/dropped), គិត → **kit** (final ត).

### 2. Onset consonants — how each letter is typed
The clearest, most stable part. Note people type **ច/ជ as "j"** (not "ch") and mark
aspiration with an **h** (ខ→kh, ថ→th, ផ→ph):

| ក k | ខ kh | គ k | ឃ kh | ង ng | ច j | ឆ ch | ជ j | ឈ ch | ញ nh |
|-----|------|-----|------|------|-----|------|-----|------|------|
| **ដ d** | **ឋ th** | **ឌ d** | **ណ n** | **ត t** | **ថ th** | **ទ t** | **ធ th** | **ន n** | **ប b** |
| **ផ ph** | **ព p** | **ភ ph** | **ម m** | **យ y** | **រ r** | **ល l** | **វ v** | **ស s** | **ហ h** |

A **subscript** (coeng) consonant just joins the onset: ស្រ → **sr**, ភ្ន → **phn**,
ក្ដ → **kd**, ខ្ម → **khm**.

### 3. Vowels depend on the consonant's *series* (the big one)
Every Khmer consonant belongs to one of two series, and **the same vowel sign is typed
differently in each**. This is the single biggest reason spellings vary:

- **a-series** consonants: ក ខ ច ឆ ដ ឋ ណ ត ថ ប ផ ស ហ ឡ អ
- **o-series** consonants: គ ឃ ង ជ ឈ ញ ឌ ឍ ទ ធ ន ព ភ ម យ រ ល វ

| vowel | a-series | o-series | | vowel | a-series | o-series |
|-------|----------|----------|-|-------|----------|----------|
| (none) | o | o | | ា | **a** | **ea** |
| ិ | e | i | | ី | ey | i |
| ុ | o | u | | ូ | o | u |
| េ | e | e | | ែ | ae | ea |
| ើ | er | er | | ៀ | ie | ie |
| ោ | ao | ou | | ៅ | ov | ov |
| ុំ / ំ | om | um | | ាំ | am | oam |

The clearest example: **ណា → na** (ណ is a-series → "a") but **មាស → meas** (ម is o-series →
"ea"). Same ា, two spellings.

### And the natural variation people read through
The *same* word is often typed a few ways, and everyone still reads it — these are the
interchangeable pairs:

- **o ↔ u**: som / sum, tum / tom
- **ei ↔ ey**: srei / srey
- **ae ↔ e**, **a ↔ ea**
- an optional trailing **-h** for a final glottal: te / teh, na / nah

## How well the pattern predicts (honest number)

Running the rule *backwards* on the words already in the database — regenerate each word's
spelling and check it against what people actually typed — the single best guess **exactly
matches ~48%** of the time, and most misses are one vowel off (a readable near-miss). That's
expected: Sing Khmer is informal, so a fixed rule can't nail every personal choice. It's good
enough to **propose** spellings for new words, which is exactly what `VERIFY_WORDS.md` is for.

**But exact-match is the wrong yardstick.** Because there's no single correct spelling, what the
engine actually optimizes is **recall** — *if a spelling weren't stored, would we still find the
word?* The romanizer generates plausible *variants* of every word (not just one guess) and feeds
them into the engine, which lifts recall from ~38% (fuzzy only) to **~79%**. See `STRATEGY.md` for
the full picture and `scripts/recall.py` to measure it.

## Try it

```
PYTHONPATH=src python scripts/romanize.py ក្ដៅ ខ្មៅ គុយទាវ   # predict specific words
PYTHONPATH=src python scripts/romanize.py --table words.txt   # a markdown table
PYTHONPATH=src python scripts/romanize.py --accuracy          # the round-trip score
```
