"""Smoke test over the labeled days: the eval runs and the error stays sane."""

from __future__ import annotations

import json
from pathlib import Path

from punchcard.rules import load_rules
from scripts.eval_days import DAYS_DIR, main, score_day

REQUIRED_KINDS = {"lecture_qt", "lecture_web", "lunch", "sleep", "micro"}


def test_the_day_set_covers_the_cases_the_engine_has_to_handle():
    kinds = set()
    for path in DAYS_DIR.glob("*.json"):
        day = json.loads(path.read_text())
        kinds |= {s["kind"] for s in day["segments"]}
    assert 6 <= len(list(DAYS_DIR.glob("*.json"))) <= 10
    assert REQUIRED_KINDS <= kinds


def test_every_labeled_day_scores_within_fifteen_minutes():
    rules = load_rules()
    for path in sorted(DAYS_DIR.glob("*.json")):
        name, label, _engine, err = score_day(Path(path), rules)
        assert label > 0, name
        assert abs(err) < 15.0, f"{name} off by {err:.2f} min"


def test_eval_prints_the_summary_line(capsys):
    assert main() == 0
    out = capsys.readouterr().out
    line = [x for x in out.splitlines() if x.startswith("punchcard-eval ")]
    assert len(line) == 1
    fields = dict(part.split("=") for part in line[0].split()[1:])
    assert int(fields["days"]) >= 6
    assert float(fields["mean_abs_error_min"]) <= float(fields["max_abs_error_min"])
