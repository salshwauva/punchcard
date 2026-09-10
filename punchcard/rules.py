"""Load rules.toml and classify one sample.

Nothing here knows an app name or a course number. Those live in rules.toml.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "rules.toml"


@dataclass(frozen=True)
class Category:
    name: str
    billable: bool
    idle_closes: bool
    app_any: tuple[str, ...]
    title_any: tuple[str, ...]


@dataclass(frozen=True)
class Rules:
    interval_s: int
    idle_threshold_s: float
    default_category: str
    categories: tuple[Category, ...]

    def get(self, name: str) -> Category:
        for cat in self.categories:
            if cat.name == name:
                return cat
        raise KeyError(f"no category {name!r} in rules")


def load_rules(path: Path | str = DEFAULT_RULES_PATH) -> Rules:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    settings = raw["settings"]
    cats = tuple(
        Category(
            name=name,
            billable=bool(body["billable"]),
            idle_closes=bool(body["idle_closes"]),
            app_any=tuple(body.get("app_any", ())),
            title_any=tuple(body.get("title_any", ())),
        )
        for name, body in raw["category"].items()
    )
    rules = Rules(
        interval_s=int(settings["interval_s"]),
        idle_threshold_s=float(settings["idle_threshold_s"]),
        default_category=str(settings["default_category"]),
        categories=cats,
    )
    rules.get(rules.default_category)  # fail loudly on a typo in the toml
    return rules


def classify(app: str, title: str | None, rules: Rules) -> Category:
    """Title match wins over app match, so a lecture in Chrome is a lecture."""
    haystack = (title or "").lower()
    if haystack:
        for cat in rules.categories:
            if any(needle.lower() in haystack for needle in cat.title_any):
                return cat
    for cat in rules.categories:
        if app in cat.app_any:
            return cat
    return rules.get(rules.default_category)
