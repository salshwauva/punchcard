"""SQLite access. The collector appends to samples; replay rebuilds the rest.

No command in this package updates or deletes a row in samples.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .rules import Rules
from .sessions import (
    Correction,
    Sample,
    Session,
    apply_corrections,
    sessionize,
)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "punchcard.db"


def connect(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def append_sample(
    conn: sqlite3.Connection,
    ts: datetime,
    app: str,
    title: str | None,
    idle_s: float,
    degraded: bool = False,
    source: str = "collector",
    bundle_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO samples (ts_utc, app, bundle_id, title, idle_s, degraded, source)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts.isoformat(), app, bundle_id, title, idle_s, int(degraded), source),
    )
    conn.commit()


def read_samples(conn: sqlite3.Connection, day: str) -> list[Sample]:
    rows = conn.execute(
        "SELECT ts_utc, app, title, tab_title, idle_s FROM samples"
        " WHERE ts_utc LIKE ? ORDER BY ts_utc",
        (f"{day}%",),
    ).fetchall()
    return [
        Sample(
            ts=datetime.fromisoformat(r["ts_utc"]),
            app=r["app"],
            title=r["title"] or r["tab_title"],
            idle_s=r["idle_s"],
        )
        for r in rows
    ]


def read_corrections(conn: sqlite3.Connection, day: str) -> list[Correction]:
    rows = conn.execute(
        "SELECT start_utc, end_utc, category, note FROM corrections"
        " WHERE day = ? ORDER BY start_utc",
        (day,),
    ).fetchall()
    return [
        Correction(
            start=datetime.fromisoformat(r["start_utc"]),
            end=datetime.fromisoformat(r["end_utc"]),
            category=r["category"],
            note=r["note"],
        )
        for r in rows
    ]


def add_correction(
    conn: sqlite3.Connection,
    day: str,
    start: datetime,
    end: datetime,
    category: str,
    note: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO corrections (day, start_utc, end_utc, category, note)"
        " VALUES (?, ?, ?, ?, ?)",
        (day, start.isoformat(), end.isoformat(), category, note),
    )
    conn.commit()


def replay_day(conn: sqlite3.Connection, day: str, rules: Rules) -> list[Session]:
    """Rebuild one day of derived rows from samples plus corrections."""
    result = apply_corrections(
        sessionize(read_samples(conn, day), rules),
        read_corrections(conn, day),
        rules,
    )
    conn.execute("DELETE FROM sessions WHERE day = ?", (day,))
    conn.execute("DELETE FROM timesheet WHERE day = ?", (day,))
    conn.executemany(
        "INSERT INTO sessions (day, start_utc, end_utc, category, billable, reason)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                day,
                s.start.isoformat(),
                s.end.isoformat(),
                s.category,
                int(s.billable),
                s.reason,
            )
            for s in result
        ],
    )
    totals: dict[str, tuple[float, bool]] = {}
    for s in result:
        minutes, _ = totals.get(s.category, (0.0, s.billable))
        totals[s.category] = (minutes + s.minutes, s.billable)
    conn.executemany(
        "INSERT INTO timesheet (day, category, minutes, billable) VALUES (?, ?, ?, ?)",
        [(day, cat, mins, int(bill)) for cat, (mins, bill) in sorted(totals.items())],
    )
    conn.commit()
    return result
