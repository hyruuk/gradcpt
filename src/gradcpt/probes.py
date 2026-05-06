"""Experience-sampling probe scheduling and item definitions.

The actual slider rendering lives in :mod:`gradcpt.routines.probe_loop` (which
depends on PsychoPy). This module is pure-Python so the scheduling logic is
unit-testable without a display.
"""
from __future__ import annotations

import random as _random
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Sequence

import yaml

from .config import ProbeConfig


@dataclass(frozen=True)
class ProbeItem:
    name: str
    text: str
    low_anchor: str
    high_anchor: str
    fixed_position: bool = False


def load_probe_items(path: Path | None) -> list[ProbeItem]:
    """Load probe items from a YAML file, or the bundled default if ``path`` is None."""
    if path is None:
        path = Path(str(files("gradcpt.data") / "default_probes.yaml"))
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    items_data = data.get("items", [])
    items = [
        ProbeItem(
            name=item["name"],
            text=item["text"],
            low_anchor=item["low_anchor"],
            high_anchor=item["high_anchor"],
            fixed_position=bool(item.get("fixed_position", False)),
        )
        for item in items_data
    ]
    if not items:
        raise ValueError(f"No probe items defined in {path}")
    if sum(1 for i in items if i.fixed_position) > 1:
        raise ValueError("At most one probe item may have fixed_position=True")
    return items


def order_items_for_probe(
    items: Sequence[ProbeItem], rng: _random.Random
) -> list[ProbeItem]:
    """Return the presentation order for one probe.

    Items with ``fixed_position=True`` are appended last (in the order they
    appear in the input); the remaining items are shuffled.
    """
    flexible = [i for i in items if not i.fixed_position]
    fixed = [i for i in items if i.fixed_position]
    flex_copy = list(flexible)
    rng.shuffle(flex_copy)
    return flex_copy + fixed


class ProbeScheduler:
    """Schedules the next experience-sampling probe trial.

    Probes fire on trial ``next_trial`` if ``cfg.enabled`` is True. After a
    probe runs, call :meth:`advance` to draw a new ``next_trial``.
    """

    def __init__(self, cfg: ProbeConfig, rng: _random.Random):
        self.cfg = cfg
        self.rng = rng
        self._next_trial = self._draw_next(0)

    @property
    def next_trial(self) -> int:
        return self._next_trial

    def is_due(self, trial_idx: int) -> bool:
        return self.cfg.enabled and trial_idx == self._next_trial

    def advance(self, trial_idx: int) -> None:
        self._next_trial = self._draw_next(trial_idx)

    def _draw_next(self, after_trial: int) -> int:
        return after_trial + self.rng.randint(self.cfg.next_es_min, self.cfg.next_es_max)
