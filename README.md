# Sing Khmer Engine

Cambodians commonly type Khmer phonetically with Latin letters ("Sing Khmer") instead of Khmer
script — for example writing `jg` or `jhg` for ចឹង — across chat apps, TikTok, and YouTube
search. Because there is no standardized romanization for casual chat Khmer, the same word gets
spelled many different ways by different people. **Sing Khmer Engine** converts this romanized
input back into proper Khmer script, offering a ranked list of suggestions as the user types.
It's the first build stage of a larger effort whose goal is a mobile keyboard.

> Full project context, decisions, and the roadmap live in [`CLAUDE.md`](./CLAUDE.md).

## Status

The Python conversion engine (Phase 1 of the roadmap) is built and working: vocabulary loading,
Khmer-syllable segmentation, phonetic-spelling generation, a reverse-index lookup, fuzzy
matching, and whole-sentence decoding (works with or without spaces between words). It currently
knows **1,244 words**.

On top of the engine sits a small FastAPI web app (`api/`) — a public converter at `/`, plus a
reviewer dashboard at `/review` where invited helpers verify words people typed and submit
accepted corrections back to `data/vocabulary.csv` as a GitHub pull request. This is live on
Vercel; see [`docs/DEPLOY.md`](docs/DEPLOY.md) for how it's deployed and how the review workflow
works.

Next up is Phase 2 (an Android keyboard shell) — see `CLAUDE.md` for the detailed plan.

## Project layout

```
sing-khmer-engine/
├── src/sing_khmer_engine/   # the engine: vocabulary, KCC segmentation, romanizer,
│                            # reverse index, fuzzy matching, lookup/decode
├── api/                     # FastAPI web app: converter API, reviewer accounts,
│                            # admin/review-queue routes, storage layer
├── webui/                   # static frontend for the converter and review dashboard
├── scripts/                 # CLIs: convert, diagnose, romanize, vocabulary tooling,
│                            # backups, feedback export/review
├── tests/                   # pytest suite (engine + API)
├── data/                    # vocabulary.csv (the live dictionary), English wordlist
├── docs/                    # design docs, deployment guide, review workflow
├── requirements.txt         # runtime dependencies (web app only — the engine itself
│                            # is pure standard library)
├── requirements-dev.txt     # development/test dependencies
└── pytest.ini               # pytest configuration
```

## Getting started

To work on the engine only (no web app, no extra dependencies):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                             # runs the full test suite

# Try it out
PYTHONPATH=src python scripts/convert.py "nhslbong"
PYTHONPATH=src python scripts/diagnose.py "srolan"
```

To run the web app locally:

```bash
pip install -r requirements.txt
PYTHONPATH=src uvicorn api.index:app --reload      # http://localhost:8000
```

With no database configured it falls back to a local SQLite file — no setup needed. See
[`docs/DEPLOY.md`](docs/DEPLOY.md) for deploying this to Vercel + Neon.

## Dependency management

This project uses **`venv` + `requirements.txt`** rather than Poetry or uv — the lowest-friction
choice for a solo-developer project. `requirements.txt` holds the web app's runtime dependencies
(the engine itself needs none) and `requirements-dev.txt` adds test/dev tools.
