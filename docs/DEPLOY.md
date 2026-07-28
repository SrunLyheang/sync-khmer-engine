# Running Sing Khmer online (and trusting the data you collect)

The point of this version isn't polish — it's to get the converter in front of your friends and
learn how people really type, so the vocabulary grows from real usage instead of spreadsheets.

## How you can tell which data is right

Short answer: **you never ask users whether the output was right — you watch what they do.**
Informal romanization has no correct spelling, so the app ranks evidence instead of pretending
to know. Strongest first:

| What happened | What it proves | Where it lands |
|---|---|---|
| Picked a different word, then **copied** it | Strongest — they acted on it, not just claimed it | `word_choices` |
| **Copied** with no edits | The whole output was accepted as-is | `confirmations` |
| Answered the inline "what should this be?" | They told us, about that exact word | `corrections` (inline) |
| Used the form at the bottom | Weakest — anyone can type anything | `corrections` (form) |

On top of that, every row counts **how many _different_ people** produced it. One person can be
wrong or joking; five independent people agreeing is as close to truth as this problem gets.

**Nothing is ever written into `data/vocabulary.csv` automatically.** The export ranks the
evidence so your review time goes to the top of the list — you stay the judge.

## How you can tell if the app has the words people want

Open `/admin?token=…`. The number to watch is **"words we couldn't convert"** — the share of
everything typed that your dictionary is still missing. Watch it fall as you add words. The same
page lists the top missing spellings and the words people most often had to correct by hand.

## Run it on your machine

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src uvicorn api.index:app --reload      # http://localhost:8000
```

With no database configured it uses a local SQLite file — zero setup. Test it **on your phone**
(same wifi), since that's how it'll actually be used:

```bash
PYTHONPATH=src uvicorn api.index:app --host 0.0.0.0 --port 8000
```

## Deploy to Vercel

These steps need your accounts, so they're yours to do. Everything else is committed.

1. **Import the repo** at [vercel.com](https://vercel.com) → *Add New Project*. The Python
   function is detected automatically.
2. **Add Postgres**: project → *Storage* → **Neon**. It sets `DATABASE_URL` for you.
3. **Set environment variables**:
   - `SECRET_KEY` — any long random string. Signs session cookies; without it, sessions reset on
     every deploy and your per-person counts get noisier.
   - `ADMIN_TOKEN` — a long random string. Without it `/admin` stays a 404 for everyone.
4. **Deploy**, then check `/api/health` shows `"storage":"postgres"`.
5. **Share the link.**

### Your data will not vanish

That was a real risk in the first version and it's now fixed properly:

- **Neon is a separate managed database.** Deploys replace your app, never the database — the
  data persists across every deploy.
- **The app refuses to fail silently.** If it's running on Vercel with no `DATABASE_URL`, it will
  *not* quietly write to the temporary disk and lose everything. `/api/health` returns **503
  degraded** and writes are declined, so you find out immediately instead of a month later.
- **Backups you control:** `PYTHONPATH=src python scripts/backup_db.py backups/` dumps every
  table to a timestamped JSON file. Neon also has point-in-time restore.

### Troubleshooting: "Database shows nothing" or Degraded Status

If you attached Postgres in Vercel but `/api/health` still shows `degraded` or your Neon table browser shows nothing:

1. **Redeploy after adding the integration (Most common cause):** Vercel environment variables only apply to deployments created *after* the environment variables are set. Attaching the Neon integration does not retroactively update an already-running deployment. Go to Vercel → Deployments → **Redeploy** (or push a new commit).
2. **Check `/api/health`:** Visit `/api/health` on your deployed app. It performs a live database test and reports:
   - `env_var`: Which environment variable was matched (`DATABASE_URL`, `POSTGRES_URL`, `DATABASE_URL_UNPOOLED`, `POSTGRES_URL_NON_POOLING`, or `NEON_DATABASE_URL`). If none are set, `checked_env_vars` lists all names searched.
   - `connected`: `true` when database connection succeeds. Returns `503` with `error_type` and `error` text if connection fails.
   - `tables`: Shows current row counts for `sessions`, `conversions`, and `corrections`.
3. **Tables appear on first visit:** Schema migrations run automatically when `/api/health` or write endpoints are called. Simply visiting `/api/health` creates the database tables so they appear in your Neon console table browser.

## Where submitted words actually go

**Into the database, not into a file.** Nothing in the repo updates itself when someone submits
a word, so there is no file to open and no `git pull` that brings the data down. Three ways to
read it, easiest first:

1. **`/admin?token=…` on the deployed site.** Lists the words people sent, the words the engine
   couldn't convert, and the words people corrected by hand. Each table has a **download CSV**
   link — that file opens directly in VS Code, Excel or Sheets. This is the one to reach for
   when the data is on Vercel, because it needs no connection string on your machine.
2. **`python scripts/show_feedback.py`** — the same three views printed in the terminal. No
   `ADMIN_TOKEN`, no spreadsheet. It prints the database it read first, so an empty result tells
   you *which* empty database you're looking at (usually: you ran it locally while the data is
   in Neon — prefix the command with `DATABASE_URL="<from Vercel>"`).
3. **`scripts/export_feedback.py`** for a formatted `.xlsx`, when you're sending a verification
   batch to friends rather than reading it yourself.

The bottom of `/admin` names the database it read, so "0 rows" is never ambiguous.

## Getting the data back into the dictionary

```bash
DATABASE_URL="<from Vercel>" PYTHONPATH=src python scripts/export_feedback.py
```

`user_feedback.xlsx` is a **snapshot taken when you run that command** — it is gitignored and
never updates on its own. Three sheets, each ranked by how many different people back it up:

1. **Engine ranked wrong** — someone chose a different word *and used it*
2. **Corrections** — what people told you a spelling means
3. **Missing words** — spellings that converted to nothing (your coverage gap)

Review, then fold what you agree with into `data/vocabulary.csv` — same as every batch so far.

## Privacy and security

What's in place:

- **The page is XSS-safe.** No user text is ever inserted as HTML (an earlier version did — it's
  now built through `textContent` only), plus a strict Content-Security-Policy and the usual
  hardening headers.
- **Sessions are issued and signed by the server** in an HttpOnly cookie, so nobody can forge an
  id or write into someone else's data.
- **No IP addresses are stored.** Rate limiting uses a daily-rotating salted hash and nothing else.
- **Emails, links and long digit runs are stripped** from text before it's ever written, so the
  most sensitive things people paste don't get saved at all.
- **Raw messages are deleted after 90 days** (`RAW_TEXT_TTL_DAYS`). All the useful signals were
  extracted when they arrived, so deleting old text costs you nothing:
  ```bash
  DATABASE_URL=... PYTHONPATH=src python scripts/purge.py     # run on a schedule
  ```
- **Junk is rejected at the door** — a correction must actually contain Khmer script, a spelling
  must actually look like a spelling. Bad data never reaches the dataset.
- **Rate limits** on every endpoint. Honest limitation: they're per serverless instance, so
  they blunt accidental floods and casual abuse rather than a determined attacker. If this goes
  properly public, move them to a shared store (Redis/Postgres).
- **`/admin` shows aggregates only** — counts and spellings, never anyone's messages.

Two things that are still on you: **tell your friends their text is saved** (easy while it's a
small group, and it's the difference between testing and surprising people), and **keep the
database private**. Before any public launch, revisit this — a public audience deserves a real
privacy policy, and you may want a shorter retention window.

## Cost

Free at this scale: Vercel hobby + Neon free tier. The engine is pure standard library, cold
starts in about half a second, and conversions take milliseconds.
