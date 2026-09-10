-- punchcard samples: append-only ground truth. Nothing downstream writes here.
-- Timestamps UTC. A row is an instant, not a duration.
CREATE TABLE IF NOT EXISTS samples (
    id        INTEGER PRIMARY KEY,
    ts_utc    TEXT NOT NULL,      -- ISO 8601, UTC
    app       TEXT NOT NULL,      -- frontmost app name
    bundle_id TEXT,               -- frontmost app bundle id
    title     TEXT,               -- AX window title (NULL when degraded)
    url_host  TEXT,               -- Chrome only; host, no scheme
    url_path  TEXT,               -- Chrome only; path, no query string ever
    tab_title TEXT,               -- Chrome only
    idle_s    REAL NOT NULL,      -- seconds since last input at sample time
    degraded  INTEGER NOT NULL DEFAULT 0,  -- 1 = a source failed; app is all we got
    source    TEXT NOT NULL DEFAULT 'collector'  -- collector, or an eval day id
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples (ts_utc);

-- Hand corrections. Replay reads them; the collector never touches them.
CREATE TABLE IF NOT EXISTS corrections (
    id        INTEGER PRIMARY KEY,
    day       TEXT NOT NULL,      -- YYYY-MM-DD the override belongs to
    start_utc TEXT NOT NULL,
    end_utc   TEXT NOT NULL,
    category  TEXT NOT NULL,      -- must name a category in rules.toml
    note      TEXT
);
CREATE INDEX IF NOT EXISTS idx_corrections_day ON corrections (day);

-- Derived. Replay drops the day's rows and rebuilds them from samples.
CREATE TABLE IF NOT EXISTS sessions (
    id        INTEGER PRIMARY KEY,
    day       TEXT NOT NULL,
    start_utc TEXT NOT NULL,
    end_utc   TEXT NOT NULL,
    category  TEXT NOT NULL,
    billable  INTEGER NOT NULL,
    reason    TEXT NOT NULL       -- what closed it: idle, gap, switch, end
);
CREATE INDEX IF NOT EXISTS idx_sessions_day ON sessions (day);

CREATE TABLE IF NOT EXISTS timesheet (
    day      TEXT NOT NULL,
    category TEXT NOT NULL,
    minutes  REAL NOT NULL,
    billable INTEGER NOT NULL,
    PRIMARY KEY (day, category)
);
