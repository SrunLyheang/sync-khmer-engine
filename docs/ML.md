# Machine learning for Sing Khmer — verdict and plan (Phase 5)

**Short answer: not yet.** A neural sequence-to-sequence model is the right *long-term*
tool for converting spellings the engine has never seen, but we don't have enough data to
train one today. Below is the honest reasoning, what we'd build first, and how we'd decide
whether ML ever beats the current rule engine.

## The suggestion

The idea (from a friend) was a **seq2seq / encoder–decoder** model — the standard
character-level "translate one string into another" architecture, like the one in the
[GeeksforGeeks seq2seq tutorial](https://www.geeksforgeeks.org/seq2seq-model-in-machine-learning/).
You feed it a romanized spelling (`bongrean`) and it emits Khmer (`បង្រៀន`), learning the
mapping from examples instead of from hand-written rules.

## Why not now: the data isn't there

Transliteration is a **low-resource** problem for Khmer, and seq2seq models are hungry:

- We currently have **869 words / 1,177 (spelling → Khmer) pairs** (avg **1.35** spellings
  per word). Many are whole-word abbreviations (`nh` → ខ្ញុំ) that don't generalize.
- Comparable studies train on **thousands to ~10,000** parallel pairs. A directly relevant
  one — rule-based **vs.** seq2seq transliteration for **Sinhala**, another abugida with
  little data — found that **rule-based wins until the corpus is large**
  ([arXiv:2501.00529](https://arxiv.org/pdf/2501.00529)). Bootstrapping methods for
  low-resource transliteration ([arXiv:1809.07807](https://arxiv.org/pdf/1809.07807)) exist
  precisely because small hand-labelled sets aren't enough on their own.
- With ~1k pairs a neural model would **overfit** — memorize our list and guess badly on
  anything new — i.e. it would be **worse** than the rules we already have, while being far
  harder to debug and ship on a phone.

So training seq2seq on today's data would cost effort and *lose* quality. That's the whole
reason ML is gated behind a data step.

## What we do instead — and it's already done

The problem seq2seq was meant to solve ("user types a word we don't know → gibberish") is
**already fixed without ML**, in Phase 2: a confidence gate passes unknown words through as
Latin instead of forcing them into nonsense Khmer. Rules + a growing vocabulary cover the
real cases today.

## The real prerequisite: build a bigger corpus first

Before any model, grow `(romanization → khmer)` from ~1k into **thousands+**:

1. **Synthesize pairs.** Run an existing **Khmer → Latin romanizer** (e.g. IDRI-LAB /
   `seanghay` Khmer tooling) over a large Khmer wordlist to auto-generate plausible
   spellings for tens of thousands of words.
2. **Mix in the real casual spellings.** Keep our hand-curated `data/vocabulary.csv` (the
   chat abbreviations a romanizer would never produce) as high-value ground truth.
3. **Result:** a corpus big enough to make training meaningful, split into train / held-out
   test sets.

## Then — and only then — try a model, and measure it (revives step 1.9)

1. Train a small **char-level seq2seq** (or a tiny Transformer) as a **fallback for unknown
   words only** — the known vocabulary still goes through the exact/rule path.
2. **Benchmark** it against the current rule engine on a held-out set of *real* chat
   examples (top-1 / top-3 accuracy). This is the skipped roadmap step **1.9**, revived.
3. **Ship it only if it beats the rules.** If it doesn't pay off, fall back to what already
   works: rule-based generation (Phase 2b) + steady vocabulary growth (I can research and
   write batches of common words to add).

## One-line summary

> Non-ML now, ML later. The gibberish problem is already solved with rules. Grow the data
> to thousands of pairs first; then try seq2seq and keep it *only if a benchmark shows it
> beats the rule engine*.
