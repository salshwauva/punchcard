"""Table-driven checks on the classifier and the sessionizer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from punchcard.rules import classify, load_rules
from punchcard.sessions import (
    Correction,
    Sample,
    apply_corrections,
    billable_minutes,
    sessionize,
    timesheet,
)

T0 = datetime(2026, 4, 6, 13, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def stream(rules, specs):
    """specs: (app, title, idle_s, count). Samples land on the 15 s grid."""
    out = []
    t = T0
    for app, title, idle, count in specs:
        for _ in range(count):
            out.append(Sample(t, app, title, idle))
            t += timedelta(seconds=rules.interval_s)
    return out


@pytest.mark.parametrize(
    "app,title,expected",
    [
        ("Code", "sessions.py", "code"),
        ("Terminal", "zsh", "code"),
        ("Google Chrome", "Piazza - CIT 5910", "browser"),
        ("QuickTime Player", "Lecture 4.mp4", "lecture"),
        ("Google Chrome", "CIT 5910 Lecture 7 - Panopto", "lecture"),
        ("Messages", "Messages", "other"),
        ("Preview", "midterm.pdf", "other"),
        ("Code", None, "code"),
    ],
)
def test_classify(rules, app, title, expected):
    assert classify(app, title, rules).name == expected


def test_one_block_runs_to_the_last_sample_plus_one_interval(rules):
    s = sessionize(stream(rules, [("Code", "a.py", 0, 40)]), rules)
    assert len(s) == 1
    assert s[0].category == "code"
    assert s[0].minutes == pytest.approx(40 * 15 / 60)
    assert s[0].reason == "end"


def test_category_switch_splits_without_losing_time(rules):
    s = sessionize(
        stream(rules, [("Code", "a.py", 0, 20), ("Messages", "Messages", 0, 20)]),
        rules,
    )
    assert [x.category for x in s] == ["code", "other"]
    assert s[0].end == s[1].start
    assert billable_minutes(s) == pytest.approx(5.0)


def test_idle_over_threshold_ends_the_block_when_the_desk_went_quiet(rules):
    # 20 ticks of work, then the same app sitting there with the idle clock running.
    samples = stream(rules, [("Code", "a.py", 0, 20)])
    samples += [
        Sample(T0 + timedelta(seconds=20 * 15 + 15 * i), "Code", "a.py", 15.0 * i)
        for i in range(1, 41)
    ]
    s = sessionize(samples, rules)
    assert len(s) == 1
    assert s[0].reason == "idle"
    # The block ends when input stopped, not when the idle sample arrived.
    assert s[0].end == T0 + timedelta(seconds=20 * 15)


def test_idle_never_ends_lecture_playback(rules):
    samples = [
        Sample(
            T0 + timedelta(seconds=15 * i), "QuickTime Player", "Lecture 4.mp4", 15 * i
        )
        for i in range(200)
    ]
    s = sessionize(samples, rules)
    assert len(s) == 1
    assert s[0].category == "lecture"
    assert s[0].minutes == pytest.approx(200 * 15 / 60)


def test_a_gap_over_two_intervals_is_a_sleep_gap(rules):
    samples = stream(rules, [("Code", "a.py", 0, 20)])
    after = T0 + timedelta(seconds=20 * 15 + 3600)
    samples += [
        Sample(after + timedelta(seconds=15 * i), "Code", "a.py", 0) for i in range(20)
    ]
    s = sessionize(samples, rules)
    assert [x.reason for x in s] == ["gap", "end"]
    assert s[0].end == T0 + timedelta(seconds=20 * 15)
    assert s[1].start == after


def test_a_gap_of_exactly_two_intervals_is_not_a_gap(rules):
    samples = [
        Sample(T0, "Code", "a.py", 0),
        Sample(T0 + timedelta(seconds=30), "Code", "a.py", 0),
    ]
    assert len(sessionize(samples, rules)) == 1


def test_correction_overrides_the_rules_for_its_span(rules):
    samples = stream(rules, [("Messages", "Messages", 0, 40)])
    s = sessionize(samples, rules)
    assert billable_minutes(s) == 0
    fixed = apply_corrections(
        s,
        [
            Correction(
                start=T0,
                end=T0 + timedelta(minutes=5),
                category="code",
                note="pair debugging over Messages",
            )
        ],
        rules,
    )
    assert billable_minutes(fixed) == pytest.approx(5.0)
    assert timesheet(fixed) == pytest.approx({"code": 5.0, "other": 5.0})


def test_correction_can_carve_the_middle_out_of_a_block(rules):
    s = sessionize(stream(rules, [("Code", "a.py", 0, 80)]), rules)
    fixed = apply_corrections(
        s,
        [
            Correction(
                start=T0 + timedelta(minutes=5),
                end=T0 + timedelta(minutes=10),
                category="other",
                note="phone call",
            )
        ],
        rules,
    )
    assert len(fixed) == 3
    assert [x.category for x in fixed] == ["code", "other", "code"]
    assert billable_minutes(fixed) == pytest.approx(15.0)


def test_empty_stream_is_empty(rules):
    assert sessionize([], rules) == []
