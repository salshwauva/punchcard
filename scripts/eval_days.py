#!/usr/bin/env python3
"""Run the session engine over every labeled day and print the error.

Each file in eval/days/ carries a sample stream and the work minutes a person
would write on the timesheet. The engine never sees the label. Error is engine
minutes minus label minutes, so a positive number means the engine billed time
Sophia did not work.

    python scripts/eval_days.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from punchcard.db import connect, replay_day
from punchcard.rules import load_rules
from punchcard.sessions import billable_minutes
from scripts.gen_days import sample_rows

DAYS_DIR = ROOT / "eval" / "days"


def load_day(conn: sqlite3.Connection, day: dict) -> None:
    conn.executemany(
        "INSERT INTO samples (ts_utc, app, title, idle_s, source)"
        " VALUES (?, ?, ?, ?, ?)",
        [
            (ts, app, title, idle, day["day"])
            for ts, app, title, idle in sample_rows(day)
        ],
    )
    conn.commit()


def score_day(path: Path, rules) -> tuple[str, float, float, float]:
    day = json.loads(path.read_text())
    conn = connect(":memory:")
    load_day(conn, day)
    sessions = replay_day(conn, day["day"], rules)
    conn.close()
    engine = billable_minutes(sessions)
    label = day["true_work_minutes"]
    return day["day"], label, engine, engine - label


def main() -> int:
    rules = load_rules()
    paths = sorted(DAYS_DIR.glob("*.json"))
    if not paths:
        print("no labeled days in eval/days/, run scripts/gen_days.py first")
        return 1
    errors = []
    print(f"{'day':<12}{'label':>9}{'engine':>9}{'error':>9}")
    for path in paths:
        name, label, engine, err = score_day(path, rules)
        errors.append(abs(err))
        print(f"{name:<12}{label:9.2f}{engine:9.2f}{err:+9.2f}")
    mean_abs = sum(errors) / len(errors)
    print(
        f"punchcard-eval days={len(errors)} "
        f"mean_abs_error_min={mean_abs:.2f} "
        f"max_abs_error_min={max(errors):.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
