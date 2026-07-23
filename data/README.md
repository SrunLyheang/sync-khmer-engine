# Data

Curated data for the Sing Khmer mapping engine.

## `vocabulary.csv` (roadmap step 1.2)

The hand-curated list of supported Khmer words/phrases. It's a CSV so you can edit it in any
spreadsheet (Excel, Google Sheets, Numbers) or a plain text editor. The engine loads it via
`sing_khmer_engine.vocabulary.load()`.

> **Note:** the rows currently in the file are a small **seed of examples to verify or replace** —
> they exist to demonstrate the format. Step 1.2 is to grow this into ~100–200 real casual/chat
> words, curated by a native Khmer speaker.

### Columns

| Column          | Required | Description |
|-----------------|----------|-------------|
| `khmer`         | yes      | The word or phrase in Khmer script. Must be unique across the file. |
| `frequency`     | yes      | Rough commonness, integer **1–5** (5 = most common). Used later to rank candidates. |
| `is_slang`      | yes      | `true` for casual/chat slang, `false` for an ordinary common word. |
| `romanizations` | no       | The Sing Khmer (Latin) spellings people type. **Separate alternatives with commas OR spaces** — both work (`jueng jg jhg` = `jueng, jg, jhg` = three spellings). For a spelling that's genuinely **two Latin words** (typed with a space, like ម្សិលមិញ), join them with a **`+`**: `msel+minh`. Optional per row. |
| `notes`         | no       | Freeform hints — usage, disambiguation, anything else. |

### Frequency scale (rough)

- **5** — extremely common, used constantly in chat
- **4** — common
- **3** — moderately common
- **2** — occasional
- **1** — rare

### Adding entries

1. Add one row per word. Keep `khmer` unique.
2. Set `frequency` to an integer 1–5 and `is_slang` to `true`/`false`.
3. In `romanizations`, list the spellings you'd actually type — separated by **spaces or commas**
   (both mean "a different spelling"): `jueng jg jhg`. Only if a single spelling is genuinely two
   Latin words (like `msel minh` for ម្សិលមិញ) join them with a **`+`**: `msel+minh`. Leave blank
   if unsure.
4. Run `pytest` (or `python -c "from sing_khmer_engine.vocabulary import load; print(len(load()))"`)
   to confirm the file still parses and validates.

The loader rejects missing required fields, out-of-range frequencies, non-boolean `is_slang`
values, and duplicate `khmer` keys — so a failing test points at the offending row number.

## `english_words.txt` (Phase 3 — code-switching)

A bundled list of common English words, one per line, used to detect English mixed into
Khmer chat ("ok", "message", "javascript") so it passes through as English instead of being
forced into Khmer. It's the [google-10000-english](https://github.com/first20hours/google-10000-english)
common-word list (MIT-licensed), minus single letters and minus short spellings that are
actually Sing Khmer abbreviations (`nh`, `sl`, `jg`, …), so detection only fires on genuine
foreign words. A word that is *both* English and a real Khmer spelling (e.g. `computer`) still
converts to Khmer first, with the English original offered as a hidden last option. Loaded by
`sing_khmer_engine.english.load_english()`; missing file simply turns detection off.
