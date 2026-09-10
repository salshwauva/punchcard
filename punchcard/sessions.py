"""Samples in, sessions out. Pure functions only: no database, no clock.

A sample is an instant. Only this module turns instants into durations.
Three things end a session: a category switch, a gap longer than two sample
intervals (the machine slept), and idle time over the threshold. Idle does not
end a session whose category says otherwise, because lecture playback is work
with no input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .rules import Rules, classify


@dataclass(frozen=True)
class Sample:
    ts: datetime
    app: str
    title: str | None
    idle_s: float


@dataclass(frozen=True)
class Session:
    start: datetime
    end: datetime
    category: str
    billable: bool
    reason: str

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0

    @property
    def day(self) -> str:
        return self.start.date().isoformat()


@dataclass(frozen=True)
class Correction:
    start: datetime
    end: datetime
    category: str
    note: str | None = None


def sessionize(samples: list[Sample], rules: Rules) -> list[Session]:
    interval = timedelta(seconds=rules.interval_s)
    gap_limit = 2 * rules.interval_s
    out: list[Session] = []
    start: datetime | None = None
    cat_name = ""
    billable = False
    last: datetime | None = None

    def close(end: datetime, reason: str) -> None:
        nonlocal start, last
        if start is not None and end > start:
            out.append(Session(start, end, cat_name, billable, reason))
        start = None
        last = None

    for s in sorted(samples, key=lambda x: x.ts):
        cat = classify(s.app, s.title, rules)
        away = cat.idle_closes and s.idle_s > rules.idle_threshold_s
        if start is not None:
            assert last is not None
            if (s.ts - last).total_seconds() > gap_limit:
                close(last + interval, "gap")
            elif cat.name != cat_name:
                close(s.ts, "switch")
        if away:
            if start is not None:
                assert last is not None
                # The desk went quiet when the idle clock started, not now.
                left = s.ts - timedelta(seconds=s.idle_s)
                close(max(start, min(left, last + interval)), "idle")
            continue
        if start is None:
            start, cat_name, billable, last = s.ts, cat.name, cat.billable, s.ts
        else:
            last = s.ts
    if start is not None and last is not None:
        close(last + interval, "end")
    return out


def _subtract(s: Session, start: datetime, end: datetime) -> list[Session]:
    if end <= s.start or start >= s.end:
        return [s]
    pieces = []
    if s.start < start:
        pieces.append(Session(s.start, start, s.category, s.billable, s.reason))
    if end < s.end:
        pieces.append(Session(end, s.end, s.category, s.billable, s.reason))
    return pieces


def apply_corrections(
    sessions: list[Session], corrections: list[Correction], rules: Rules
) -> list[Session]:
    """A correction wins over the rules for the span it covers."""
    out = list(sessions)
    for c in corrections:
        cat = rules.get(c.category)
        kept: list[Session] = []
        for s in out:
            kept.extend(_subtract(s, c.start, c.end))
        kept.append(Session(c.start, c.end, cat.name, cat.billable, "correction"))
        out = sorted(kept, key=lambda x: x.start)
    return out


def timesheet(sessions: list[Session]) -> dict[str, float]:
    """Minutes per category, over whatever sessions you hand it."""
    totals: dict[str, float] = {}
    for s in sessions:
        totals[s.category] = totals.get(s.category, 0.0) + s.minutes
    return dict(sorted(totals.items()))


def billable_minutes(sessions: list[Session]) -> float:
    return sum(s.minutes for s in sessions if s.billable)
