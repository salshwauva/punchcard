#!/usr/bin/env python3
"""Generate the labeled eval days in eval/days/.

Every day is a timeline of segments: code, browser, lecture playback, short
breaks at the desk, a lunch break, and on some days a sleep gap where the
machine writes nothing. The generator samples that timeline on the same 15 s
grid the collector uses, so segment edges land mid tick and the engine has to
approximate. The label is the sum of the work segments, which is what a person
would write down; the arithmetic list is that sum written out.

Deterministic: same seed, same files. Run it from the repo root.

    python scripts/gen_days.py
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "eval" / "days"
SEED = 20260406
INTERVAL_S = 15
# macOS blanks the display after this much quiet, and the collector then writes
# nothing. Media playback holds a power assertion, so a real lecture keeps
# sampling; a paused lecture left frontmost over lunch does not.
DISPLAY_SLEEP_S = 900

# kind -> (app, title, counts as work, generates input)
KINDS = {
    "code": ("Code", "sessions.py - punchcard", True, True),
    "terminal": ("Terminal", "zsh - punchcard", True, True),
    "browser": ("Google Chrome", "Piazza - CIT 5910", True, True),
    "lecture_qt": ("QuickTime Player", "CIT 5930 Lecture 4.mp4", True, False),
    "lecture_web": ("Google Chrome", "CIT 5910 Lecture 7 - Panopto", True, False),
    "personal": ("Messages", "Messages", False, True),
    "micro": (None, None, False, False),  # short break, app stays put
    "lunch": (None, None, False, False),
    "sleep": (None, None, False, False),  # no samples at all
}

# One line per workday: a comma separated list of "kind minutes" segments.
DAY_PLANS = [
    (
        "2026-04-06",
        "code 95, micro 3, browser 40, lunch 47, code 110, micro 4, terminal 35",
    ),
    (
        "2026-04-07",
        "code 60, lecture_qt 52, micro 5, browser 30, lunch 38, code 85, personal 20, code 40",
    ),
    (
        "2026-04-08",
        "browser 25, code 130, lunch 55, sleep 40, code 70, micro 3, lecture_web 48",
    ),
    (
        "2026-04-09",
        "code 75, micro 2, code 50, lunch 42, lecture_qt 78, browser 35, micro 4, code 25",
    ),
    (
        "2026-04-10",
        "terminal 45, browser 55, micro 6, code 65, lunch 50, code 95, sleep 25, code 30",
    ),
    (
        "2026-04-13",
        "code 120, micro 3, lecture_web 40, lunch 45, browser 60, personal 15, code 55",
    ),
    (
        "2026-04-14",
        "code 40, micro 4, terminal 70, lunch 60, lecture_qt 90, micro 5, code 45",
    ),
    (
        "2026-04-15",
        "browser 35, code 105, micro 2, lunch 40, code 60, sleep 55, terminal 50, code 20",
    ),
]
DAY_START_UTC_HOUR = 13  # 9 am Philadelphia


def parse_plan(plan: str) -> list[tuple[str, int]]:
    out = []
    for part in plan.split(","):
        kind, minutes = part.split()
        out.append((kind, int(minutes)))
    return out


def build_day(date_str: str, plan: str, rng: random.Random) -> dict:
    start = datetime.fromisoformat(date_str).replace(
        hour=DAY_START_UTC_HOUR, tzinfo=UTC
    )
    segments = []
    cursor = 0.0
    for kind, minutes in parse_plan(plan):
        # Break the minute grid so segment edges land inside a tick.
        length = minutes * 60 + rng.uniform(0, INTERVAL_S)
        segments.append(
            {
                "kind": kind,
                "start_s": cursor,
                "end_s": cursor + length,
                "minutes": round(length / 60.0, 4),
                "work": KINDS[kind][2],
            }
        )
        cursor += length

    apps: list[list[str]] = []
    app_index: dict[tuple[str, str], int] = {}
    samples = []
    last_input = 0.0
    last_app: tuple[str, str] | None = None
    pending_wake = False
    seg_i = 0
    t = 0.0
    while t < cursor:
        while seg_i < len(segments) and t >= segments[seg_i]["end_s"]:
            seg_i += 1
        if seg_i >= len(segments):
            break
        seg = segments[seg_i]
        app, title, _, makes_input = KINDS[seg["kind"]]
        quiet = seg["kind"] in ("micro", "lunch") and t - last_input > DISPLAY_SLEEP_S
        if seg["kind"] == "sleep" or quiet:
            # Nothing on screen to sample. Waking the machine takes a key press.
            pending_wake = True
            t += INTERVAL_S
            continue
        if app is None:
            if last_app is None:
                t += INTERVAL_S
                continue
            app, title = last_app
        else:
            last_app = (app, title)
        if pending_wake:
            last_input = t
            pending_wake = False
        elif makes_input and rng.random() < 0.8:
            last_input = t
        key = (app, title)
        if key not in app_index:
            app_index[key] = len(apps)
            apps.append([app, title])
        samples.append([round(t, 1), app_index[key], round(t - last_input, 1)])
        t += INTERVAL_S

    work = [s for s in segments if s["work"]]
    true_minutes = sum(s["minutes"] for s in work)
    arithmetic = [f"{s['kind']} {s['minutes']:.2f}" for s in work]
    arithmetic.append(f"sum = {true_minutes:.2f} min")
    return {
        "day": date_str,
        "seed": SEED,
        "interval_s": INTERVAL_S,
        "start_utc": start.isoformat(),
        "true_work_minutes": round(true_minutes, 4),
        "arithmetic": arithmetic,
        "segments": segments,
        "apps": apps,
        "samples": samples,
    }


def sample_rows(day: dict) -> list[tuple[str, str, str, float]]:
    """(ts_utc, app, title, idle_s) for every sample in a loaded day file."""
    start = datetime.fromisoformat(day["start_utc"])
    apps = day["apps"]
    return [
        (
            (start + timedelta(seconds=offset)).isoformat(),
            apps[idx][0],
            apps[idx][1],
            idle,
        )
        for offset, idx, idle in day["samples"]
    ]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for date_str, plan in DAY_PLANS:
        rng = random.Random(f"{SEED}:{date_str}")
        day = build_day(date_str, plan, rng)
        path = OUT_DIR / f"{date_str}.json"
        path.write_text(json.dumps(day, indent=1) + "\n")
        print(
            f"{date_str}  {len(day['samples']):5d} samples  "
            f"label {day['true_work_minutes']:7.2f} min  -> {path.name}"
        )


if __name__ == "__main__":
    main()
