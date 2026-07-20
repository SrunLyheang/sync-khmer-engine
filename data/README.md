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

| Column      | Required | Description |
|-------------|----------|-------------|
| `khmer`     | yes      | The word or phrase in Khmer script. Must be unique across the file. |
| `meaning`   | yes      | Short English gloss. |
| `frequency` | yes      | Rough commonness, integer **1–5** (5 = most common). Used later to rank candidates. |
| `is_slang`  | yes      | `true` for casual/chat slang, `false` for an ordinary common word. |
| `notes`     | no       | Freeform hints — usage, example romanizations, disambiguation. |

### Frequency scale (rough)

- **5** — extremely common, used constantly in chat
- **4** — common
- **3** — moderately common
- **2** — occasional
- **1** — rare

### Adding entries

1. Add one row per word. Keep `khmer` unique.
2. Set `frequency` to an integer 1–5 and `is_slang` to `true`/`false`.
3. Run `pytest` (or `python -c "from sing_khmer_engine.vocabulary import load; print(len(load()))"`)
   to confirm the file still parses and validates.

The loader rejects missing required fields, out-of-range frequencies, non-boolean `is_slang`
values, and duplicate `khmer` keys — so a failing test points at the offending row number.
