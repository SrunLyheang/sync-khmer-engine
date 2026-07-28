# Putting Sing Khmer online (and collecting real data)

The goal of this version is **not** a polished product — it's to get the converter in front of
your friends and learn how people really type, so the vocabulary grows from real usage instead of
hand-verified spreadsheets.

## What was built

| Piece | What it is |
|---|---|
| `api/index.py` | FastAPI app wrapping the **real Python engine** — one engine, no duplicated JS decoder |
| `webui/index.html` | The phone-first web app (live conversion, tap-to-change words, copy button) |
| `db/schema.sql` | The three tables: `sessions`, `events`, `feedback` |
| `scripts/export_feedback.py` | Pulls real usage back out as the **same Excel sheet** you already verify |
| `vercel.json` | Routes every request to the Python function |

## Run it on your own machine first

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src uvicorn api.index:app --reload
# open http://localhost:8000
```

With no database configured it writes to a local SQLite file, so it works instantly with zero
setup. Check it's alive at `http://localhost:8000/api/health`.

**Test it from your phone** (same wifi) — this is a phone app, so try it on a phone:

```bash
PYTHONPATH=src uvicorn api.index:app --host 0.0.0.0 --port 8000
# then browse to http://<your-computer-ip>:8000 on your phone
```

## Put it on the internet (Vercel)

These steps need your accounts, so you have to do them — everything else is committed and ready.

1. **Push the branch and import the repo.** On [vercel.com](https://vercel.com) → *Add New Project*
   → import `sing-khmer-engine-2`. Vercel detects the Python function automatically; no build
   settings to change.
2. **Add a database.** In the project → *Storage* → add **Neon Postgres** (free tier is plenty).
   Vercel injects the `DATABASE_URL` environment variable for you. Without it the app still runs,
   but data disappears on every deploy — Vercel's disk is temporary.
3. **Create the tables.** Either just open the site once (the app creates them on first request),
   or run `psql "$DATABASE_URL" -f db/schema.sql`.
4. **Deploy**, then visit `/api/health`. You want to see `"storage":"postgres"`. If it says
   `sqlite`, `DATABASE_URL` isn't set.
5. **Share the link** with your friends.

## Getting the data back into the dictionary

This is the whole point — the loop that replaces hand-curated batches:

```bash
DATABASE_URL="<from Vercel>" PYTHONPATH=src python scripts/export_feedback.py
```

You get `user_feedback.xlsx` with two sheets, both ranked by how often each spelling appeared:

- **Corrections from users** — someone explicitly said "I typed X, it means Y"
- **Words we couldn't convert** — spellings the engine failed on, i.e. exactly what's missing

Verify them the same way as every previous batch, then fold them into `data/vocabulary.csv`.
Real users now tell you which words matter, instead of you guessing from a frequency list.

## About the data you're collecting

You chose to save everything people type, so the app is honest about it rather than quiet:

- A **visible notice in Khmer and English** on the page says text is saved to improve the converter.
- Each browser gets a **random ID** stored locally. **No names, no phone numbers, no IP addresses,
  no fingerprinting** — you can't tell who wrote what, only that it was the same browser.
- There's an **off switch** ("Don't save my text") that the app honours.
- It logs the **finished text after someone stops typing**, not every keystroke — less noise, and
  far less data sitting around.
- The notice asks people not to type passwords or private information.

Two things worth doing before you share it: tell your friends plainly that their text is saved
(easy while it's a small group, and it's the difference between testing and surprising people),
and keep the database private — don't publish the raw table, since it's people's real messages.
When you eventually launch publicly, revisit this: a public audience needs a real privacy policy,
and you may want to shorten how long rows are kept.

## Cost

Free on Vercel's hobby tier plus Neon's free tier at this scale. The engine is pure standard
library and cold-starts in about half a second; conversions take milliseconds.
