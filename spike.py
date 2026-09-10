#!/Library/Frameworks/Python.framework/Versions/3.13/bin/python3
# Phase 0 spike. Throwaway: proves the four reads punchcard needs, from the
# framework interpreter, and triggers the two TCC prompts. Delete after Phase 0.
import subprocess

import Quartz
from AppKit import NSWorkspace
from ApplicationServices import (
    AXIsProcessTrustedWithOptions,
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    kAXFocusedWindowAttribute,
    kAXTitleAttribute,
)


def frontmost():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None, None
    return app.localizedName(), app.processIdentifier()


def ax_title(pid):
    # The True prompt option pops the Accessibility grant dialog on first run.
    if not AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True}):
        return None, "NOT TRUSTED yet: grant Accessibility in System Settings, rerun"
    ax_app = AXUIElementCreateApplication(pid)
    err, win = AXUIElementCopyAttributeValue(ax_app, kAXFocusedWindowAttribute, None)
    if err != 0 or win is None:
        return None, f"no focused window (AXError {err})"
    err, title = AXUIElementCopyAttributeValue(win, kAXTitleAttribute, None)
    if err != 0:
        return None, f"no title (AXError {err})"
    return str(title), None


def chrome_tab():
    # "is running" does not launch Chrome; a bare tell would.
    script = (
        'if application "Google Chrome" is running then\n'
        '  tell application "Google Chrome"\n'
        "    if (count of windows) > 0 then\n"
        '      return (URL of active tab of front window) & "\\n" & (title of active tab of front window)\n'
        "    end if\n"
        "  end tell\n"
        "end if\n"
        'return ""'
    )
    try:
        out = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=2
        )
    except subprocess.TimeoutExpired:
        return None, None, "TIMEOUT after 2 s (degraded path)"
    if out.returncode != 0:
        return None, None, f"osascript error: {out.stderr.strip()}"
    if not out.stdout.strip():
        return None, None, "Chrome not running or zero windows (degraded path)"
    url, _, title = out.stdout.strip().partition("\n")
    return url, title, None


def idle_seconds():
    return Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateHIDSystemState, Quartz.kCGAnyInputEventType
    )


if __name__ == "__main__":
    name, pid = frontmost()
    print(f"frontmost app : {name} (pid {pid})")
    title, err = ax_title(pid) if pid else (None, "no frontmost pid")
    print(f"ax title      : {title if err is None else 'FAIL: ' + err}")
    url, tab_title, err = chrome_tab()
    if err is None:
        print(f"chrome url    : {url}")
        print(f"chrome title  : {tab_title}")
    else:
        print(f"chrome        : {err}")
    print(f"idle seconds  : {idle_seconds():.1f}")
