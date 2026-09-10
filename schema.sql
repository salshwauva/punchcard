-- punchcard samples: append-only ground truth. Nothing downstream writes here.
-- Timestamps UTC. A row is an instant, not a duration.
CREATE TABLE IF NOT EXISTS samples (
    id        INTEGER PRIMARY KEY,
    ts_utc    TEXT NOT NULL,      -- ISO 8601, UTC
    app       TEXT NOT NULL,      -- frontmost app name
    title     TEXT,               -- AX window title (NULL when degraded)
    url_host  TEXT,               -- Chrome only; host, no scheme
    url_path  TEXT,               -- Chrome only; path, no query string ever
    tab_title TEXT,               -- Chrome only
    idle_s    REAL NOT NULL,      -- seconds since last input at sample time
    degraded  INTEGER NOT NULL DEFAULT 0  -- 1 = a source failed; app is all we got
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples (ts_utc);
