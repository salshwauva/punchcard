# Punchcard

Punchcard is a macOS activity collector. It records the frontmost app and idle
state to SQLite every 15 seconds, then turns those samples into a report of TA
work hours, so the hours never need hand timing.

## How it works

The raw samples are the ground truth. Sessions, categories and the timesheet
are derived, and any of them rebuilds from the rows.

- `punchcard/collect.py` writes one row per tick: the frontmost app, its bundle
  id, the window title, and seconds since the last input of any kind. It is the
  only writer of the `samples` table. While the display sleeps it writes
  nothing, so a gap forms and the gap rule closes the open session.
- `punchcard/sessions.py` is a pure function from samples to sessions. Three
  things end a session: the category changes, the gap to the next sample runs
  longer than two intervals, or idle time passes the threshold. Idle does not
  end lecture playback, because a lecture is work with no input.
- `rules.toml` holds every app name, title pattern and threshold. No app name
  or course number lives in the Python.
- Corrections live in their own table. Replay applies them over the rule
  output, so a hand fix survives a rebuild and never edits a raw sample.

## Setup

Use the python.org framework build of Python 3.13, not anaconda. The macOS
privacy grants attach to the interpreter path, so a new interpreter means a new
grant prompt.

    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv .venv
    .venv/bin/python -m pip install -e ".[dev]"

Punchcard needs the Accessibility grant to read window titles. Open System
Settings, Privacy and Security, Accessibility, then add `.venv/bin/python`.
Without the grant the collector still runs. It records the app name and the
idle clock, and it flags every row it writes with `degraded = 1`.

## Run

    punchcard collect                     # sample until the process stops
    punchcard collect --seconds 30        # sample for 30 seconds, then stop
    punchcard replay --day 2026-04-06     # rebuild that day from samples

To run the collector in the background, copy
`contrib/com.sophia.punchcard.plist` to `~/Library/LaunchAgents/`, replace
`PUNCHCARD_HOME` with the repo path, then load it:

    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sophia.punchcard.plist

## Test

    python -m pytest -q

`scripts/eval_days.py` grades the engine against eight labeled workdays.
`scripts/gen_days.py` builds those days from a fixed seed, apart from the
engine. Each day covers idle time at the desk, a lunch break, a sleep gap where
the machine wrote nothing, and lecture playback that has to keep counting. The
label is the sum of the work segments, which is what a person would write on a
timesheet, and each day file spells the sum out in its `arithmetic` field.
Error is engine minutes minus label minutes.

    $ python scripts/eval_days.py
    day             label   engine    error
    2026-04-06     280.66   287.75    +7.09
    2026-04-07     267.68   267.50    -0.18
    2026-04-08     273.53   276.75    +3.22
    2026-04-09     263.77   269.50    +5.73
    2026-04-10     290.86   290.00    -0.86
    2026-04-13     275.32   278.50    +3.18
    2026-04-14     245.29   249.00    +3.71
    2026-04-15     270.91   271.00    +0.09
    punchcard-eval days=8 mean_abs_error_min=3.01 max_abs_error_min=7.09

## Known limits

Most of the error is the price of the sample grid plus breaks shorter than the
five minute idle threshold, which the engine counts as work and a person would
not. Raise the threshold to an hour and the mean error climbs from 3.01 to
16.90 minutes, which is the check that the idle rule earns its place.

Without the Accessibility grant, every row carries `degraded = 1` and no window
title, so a title rule falls back to the app name alone.
