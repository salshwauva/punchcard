"""Replay rebuilds derived tables and leaves the raw table alone."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from punchcard.db import add_correction, connect, replay_day
from punchcard.rules import load_rules
from punchcard.sessions import billable_minutes

DAY = "2026-04-06"
T0 = datetime(2026, 4, 6, 13, 0, tzinfo=UTC)


def raw_fingerprint(conn: sqlite3.Connection) -> tuple[int, str]:
    rows = conn.execute("SELECT * FROM samples ORDER BY id").fetchall()
    digest = hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest()
    return len(rows), digest


@pytest.fixture
def conn():
    c = connect(":memory:")
    c.executemany(
        "INSERT INTO samples (ts_utc, app, title, idle_s, source) VALUES (?, ?, ?, ?, ?)",
        [
            (
                (T0 + timedelta(seconds=15 * i)).isoformat(),
                "Code" if i < 40 else "Messages",
                "sessions.py",
                0.0,
                "test",
            )
            for i in range(80)
        ],
    )
    c.commit()
    yield c
    c.close()


def test_replay_writes_sessions_and_timesheet(conn):
    rules = load_rules()
    replay_day(conn, DAY, rules)
    cats = [
        r[0] for r in conn.execute("SELECT category FROM sessions ORDER BY start_utc")
    ]
    assert cats == ["code", "other"]
    sheet = dict(conn.execute("SELECT category, minutes FROM timesheet").fetchall())
    assert sheet == pytest.approx({"code": 10.0, "other": 10.0})


def test_replay_is_idempotent_and_never_touches_samples(conn):
    rules = load_rules()
    before = raw_fingerprint(conn)
    first = replay_day(conn, DAY, rules)
    after_one = raw_fingerprint(conn)
    second = replay_day(conn, DAY, rules)
    after_two = raw_fingerprint(conn)

    assert before == after_one == after_two
    assert before[0] == 80
    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2


def test_a_correction_changes_the_timesheet_but_not_the_samples(conn):
    rules = load_rules()
    before = raw_fingerprint(conn)
    plain = billable_minutes(replay_day(conn, DAY, rules))
    add_correction(
        conn,
        DAY,
        T0 + timedelta(minutes=10),
        T0 + timedelta(minutes=15),
        "code",
        "office hours in Messages",
    )
    corrected = billable_minutes(replay_day(conn, DAY, rules))
    assert plain == pytest.approx(10.0)
    assert corrected == pytest.approx(15.0)
    assert raw_fingerprint(conn) == before


def test_dropping_the_derived_tables_loses_nothing(conn):
    rules = load_rules()
    expected = replay_day(conn, DAY, rules)
    conn.execute("DELETE FROM sessions")
    conn.execute("DELETE FROM timesheet")
    conn.commit()
    assert replay_day(conn, DAY, rules) == expected
