-- Sing Khmer web app — Postgres schema (Neon / Vercel Postgres).
-- The app creates these automatically on first request, but running this by hand
-- makes the shape explicit and lets you set up indexes ahead of time.
--
--   psql "$DATABASE_URL" -f db/schema.sql

-- One row per browser. `id` is a random UUID generated in the browser and kept in
-- localStorage — it is NOT tied to a person, phone number, or IP address.
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    created_at  TIMESTAMP,
    consent     BOOLEAN
);

-- What people typed. `kind` is 'typed' (text that settled after a pause) or 'copied'.
-- Keystrokes are NOT recorded — only the finished text of an editing burst.
CREATE TABLE IF NOT EXISTS events (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT,
    ts          TIMESTAMP,
    kind        TEXT,
    input_text  TEXT,
    output_text TEXT
);

-- Explicit corrections: "I typed X, it should be Y". The highest-value signal.
CREATE TABLE IF NOT EXISTS feedback (
    id             BIGSERIAL PRIMARY KEY,
    session_id     TEXT,
    ts             TIMESTAMP,
    spelling       TEXT,
    expected_khmer TEXT,
    note           TEXT
);

CREATE INDEX IF NOT EXISTS events_ts_idx    ON events (ts);
CREATE INDEX IF NOT EXISTS feedback_ts_idx  ON feedback (ts);
