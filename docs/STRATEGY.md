# Handling "everyone spells it differently"

The hardest truth about Sing Khmer: **there is no single correct spelling.** The same word is
typed many ways — ពោត is `pout` or `put`, វត្ត is `vat` or `wat`, ក្រុមហ៊ុន is `kromhun` or
`kromhon`. You can't write down "the" spelling, and you shouldn't try.

So the engine's goal is **coverage, not correctness**: not "predict the one right spelling" but
"whatever a person reasonably types, land on the right word." That's achieved with three layers.

## The three layers of coverage

1. **Collected spellings (ground truth).** Every spelling you and your team actually type is
   stored, and one word can hold many (`ពោត → pout, put`). This is the backbone — and the *only*
   thing that can capture heavily-abbreviated forms that follow no rule (`យើង → yg`, `ដឹង → dg`,
   `និយាយ → yy`). Keep collecting these for common words.

2. **Generated variants (auto-coverage).** For every word, the romanizer
   (`sing_khmer_engine.romanizer`) generates a handful of *plausible* spellings from the learned
   pattern — both consonant-series vowel readings, final រ dropped or kept, final ស/ះ as "s" or
   "h", and so on. These fill the long tail so a spelling nobody has typed yet (`sko` for ស្ករ,
   `seh` for សេះ) still matches. They're always scored **below** collected spellings, so a real
   spelling always wins.

3. **Fuzzy matching.** A near-miss or typo (1–2 letters off) still resolves to the closest known
   spelling, so you don't need to enumerate every variation.

On top, **frequency ranking** decides between words when a spelling is ambiguous (homophones).

## The metric that matters: recall

Because there's no single right answer, exact-match ("did we predict the exact string?") is the
wrong yardstick — it caps out around 50% no matter what. The real question is **recall**: *if a
real spelling weren't stored, would the engine still find the right word?* Run it with:

```
PYTHONPATH=src python scripts/recall.py
```

The generated-variant layer roughly **doubles recall — from ~38% (fuzzy only) to ~79%.** The
remaining misses are arbitrary abbreviations (`yg`, `dg`) that no rule can invent; those must be
collected by hand.

## How to plan your effort

- **Grow the DB with common, everyday chat words** — that's where variety and volume are worth
  capturing. Don't chase rare, formal, or technical words; people spell those inconsistently or
  never type them at all.
- **Store several real spellings per common word** as you and your team notice them — each one
  raises recall and teaches the generator.
- **Let the generator + fuzzy handle the long tail.** You don't have to write down every spelling
  — only the ones the rules can't guess (short abbreviations).
- **English loanwords stay English.** `beer`, `police`, `video`, `computer` are stored with their
  English spelling so typing the English word yields the Khmer script — no need to invent a Khmer
  romanization for them.

In short: you're not building a dictionary of "correct" spellings. You're teaching the engine to
recognize *however people actually type*, and measuring it by how often it lands on the right word.
