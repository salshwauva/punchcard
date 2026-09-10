"""punchcard command line: collect samples, replay a day."""

from __future__ import annotations

import argparse
from pathlib import Path

from .db import DEFAULT_DB_PATH, connect, replay_day
from .rules import DEFAULT_RULES_PATH, load_rules
from .sessions import timesheet


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="punchcard")
    p.add_argument("--db", default=str(DEFAULT_DB_PATH))
    p.add_argument("--rules", default=str(DEFAULT_RULES_PATH))
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="sample the desktop into the samples table")
    c.add_argument("--seconds", type=float, default=None, help="stop after N seconds")

    r = sub.add_parser("replay", help="rebuild one day of sessions and timesheet")
    r.add_argument("--day", required=True, help="YYYY-MM-DD, UTC")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    rules = load_rules(Path(args.rules))
    conn = connect(Path(args.db))

    if args.cmd == "collect":
        from .collect import ax_trusted, run

        if not ax_trusted():
            print("no Accessibility grant: titles will be NULL, app name only")
        written = run(conn, rules.interval_s, args.seconds)
        total = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
        print(f"wrote {written} samples, {total} rows in samples")
        return 0

    sessions = replay_day(conn, args.day, rules)
    for s in sessions:
        print(
            f"{s.start.time().isoformat()} {s.end.time().isoformat()} "
            f"{s.category:<8} {s.minutes:6.1f} min  {s.reason}"
        )
    for cat, minutes in timesheet(sessions).items():
        print(f"total {cat:<8} {minutes:6.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
