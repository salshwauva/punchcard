"""The sampler. Only this module writes to the samples table.

One read per tick: frontmost app, its window title, seconds since any input.
Every read is wrapped: a failed title read writes a degraded sample with the
app name, it never kills the loop. While the display sleeps the loop writes
nothing, so the gap rule closes the open session on its own.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime

import Quartz
from AppKit import NSWorkspace
from ApplicationServices import (
    AXIsProcessTrustedWithOptions,
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    kAXFocusedWindowAttribute,
    kAXTitleAttribute,
)

from .db import append_sample


def frontmost() -> tuple[str | None, str | None, int | None]:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None, None, None
    return app.localizedName(), app.bundleIdentifier(), app.processIdentifier()


def ax_trusted(prompt: bool = False) -> bool:
    return bool(AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": prompt}))


def ax_title(pid: int) -> str | None:
    """None means degraded: no Accessibility grant, or no titled window."""
    if not ax_trusted():
        return None
    try:
        ax_app = AXUIElementCreateApplication(pid)
        err, win = AXUIElementCopyAttributeValue(
            ax_app, kAXFocusedWindowAttribute, None
        )
        if err != 0 or win is None:
            return None
        err, title = AXUIElementCopyAttributeValue(win, kAXTitleAttribute, None)
        if err != 0 or title is None:
            return None
        return str(title)
    except (ValueError, TypeError, RuntimeError):
        return None


def idle_seconds() -> float:
    # Any input event, not mouse only: keyboard-only work must not read as away.
    return float(
        Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateHIDSystemState, Quartz.kCGAnyInputEventType
        )
    )


def display_asleep() -> bool:
    return bool(Quartz.CGDisplayIsAsleep(Quartz.CGMainDisplayID()))


def sample_once(conn: sqlite3.Connection) -> bool:
    """Write one sample. Returns False when the tick wrote nothing."""
    if display_asleep():
        return False
    name, bundle_id, pid = frontmost()
    if name is None:
        return False
    title = ax_title(pid) if pid is not None else None
    append_sample(
        conn,
        ts=datetime.now(UTC),
        app=name,
        title=title,
        idle_s=idle_seconds(),
        degraded=title is None,
        source="collector",
        bundle_id=bundle_id,
    )
    return True


def run(conn: sqlite3.Connection, interval_s: int, seconds: float | None = None) -> int:
    """Sample every interval_s. seconds=None runs until the process is killed."""
    written = 0
    started = next_tick = time.monotonic()
    while True:
        written += int(sample_once(conn))
        next_tick += interval_s
        if seconds is not None and next_tick - started > seconds:
            break
        time.sleep(max(0.0, next_tick - time.monotonic()))
    return written
