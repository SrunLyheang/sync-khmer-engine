# Sing Khmer Engine

Cambodians commonly type Khmer phonetically with Latin letters ("Sing Khmer") instead of Khmer
script — for example writing `jg` or `jhg` for ចឹង — across chat apps, TikTok, and YouTube
search. Because there is no standardized romanization for casual chat Khmer, the same word gets
spelled many different ways by different people. **Sing Khmer Engine** is the Python prototype of
a mapping engine that converts this romanized input back into proper Khmer script, offering a
ranked list of suggestions as the user types. It's the first build stage of a larger effort whose
goal is a mobile keyboard; this prototype exists to prove the romanized → Khmer matching approach
works before any UI is built.

> Full project context, decisions, and the roadmap live in [`CLAUDE.md`](./CLAUDE.md).

## Status

**Phase 1, step 1.1 — project scaffold.** Structure only; no engine logic yet.

## Project layout

```
sing-khmer-engine/
├── src/sing_khmer_engine/   # the engine package (phonetic rules, vocabulary, reverse index, lookup — later steps)
├── tests/                   # pytest suite
├── data/                    # vocabulary lists, phonetic rules, generated reverse index (later steps)
├── requirements.txt         # runtime dependencies
├── requirements-dev.txt     # development/test dependencies
└── pyproject.toml           # pytest configuration
```

## Getting started

```bash
# From the project root
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                             # should pass the smoke test
```

## Dependency management

This project uses **`venv` + `requirements.txt`** rather than Poetry or uv. For a solo-developer
prototype this is the lowest-friction choice: it relies only on the Python standard library, needs
no extra tooling to install, and is universally understood. `requirements.txt` holds runtime
dependencies and `requirements-dev.txt` adds test/dev tools (currently just `pytest`). If the
project grows and needs lockfiles or richer dependency resolution, migrating to Poetry or uv later
is straightforward.
