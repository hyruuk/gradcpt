from __future__ import annotations

import random
from importlib.resources import files
from pathlib import Path

import pytest

from gradcpt.config import ProbeConfig
from gradcpt.probes import ProbeItem, ProbeScheduler, load_probe_items, order_items_for_probe


def test_load_default_probes():
    items = load_probe_items(None)
    assert len(items) == 6
    names = [i.name for i in items]
    assert "confidence" in names
    confidence = next(i for i in items if i.name == "confidence")
    assert confidence.fixed_position is True


def test_load_probes_from_explicit_path():
    p = Path(str(files("gradcpt.data") / "default_probes.yaml"))
    items = load_probe_items(p)
    assert len(items) == 6


def test_load_probes_rejects_empty(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("items: []\n")
    with pytest.raises(ValueError, match="No probe"):
        load_probe_items(p)


def test_load_probes_rejects_multiple_fixed(tmp_path):
    p = tmp_path / "two_fixed.yaml"
    p.write_text(
        "items:\n"
        "  - {name: a, text: a, low_anchor: lo, high_anchor: hi, fixed_position: true}\n"
        "  - {name: b, text: b, low_anchor: lo, high_anchor: hi, fixed_position: true}\n"
    )
    with pytest.raises(ValueError, match="fixed_position"):
        load_probe_items(p)


def _items(names: list[str], fixed: list[str] = []) -> list[ProbeItem]:
    return [
        ProbeItem(
            name=n,
            text=n,
            low_anchor="lo",
            high_anchor="hi",
            fixed_position=(n in fixed),
        )
        for n in names
    ]


def test_order_items_fixed_always_last():
    items = _items(["a", "b", "c", "d", "fixed"], fixed=["fixed"])
    for seed in range(20):
        ordered = order_items_for_probe(items, random.Random(seed))
        assert ordered[-1].name == "fixed"
        assert sorted(o.name for o in ordered[:-1]) == ["a", "b", "c", "d"]


def test_order_items_no_fixed_returns_shuffled_full_set():
    items = _items(["a", "b", "c", "d"])
    ordered = order_items_for_probe(items, random.Random(0))
    assert sorted(o.name for o in ordered) == ["a", "b", "c", "d"]


def test_probe_scheduler_first_draw_in_range():
    cfg = ProbeConfig(enabled=True, next_es_min=10, next_es_max=20)
    s = ProbeScheduler(cfg, random.Random(0))
    assert 10 <= s.next_trial <= 20


def test_probe_scheduler_advance_uses_post_trial_window():
    cfg = ProbeConfig(enabled=True, next_es_min=5, next_es_max=10)
    s = ProbeScheduler(cfg, random.Random(0))
    s.advance(40)
    assert 45 <= s.next_trial <= 50


def test_probe_scheduler_disabled_is_due_returns_false():
    cfg = ProbeConfig(enabled=False, next_es_min=1, next_es_max=2)
    s = ProbeScheduler(cfg, random.Random(0))
    for t in range(10):
        assert s.is_due(t) is False


def test_probe_scheduler_is_due_at_target_only():
    cfg = ProbeConfig(enabled=True, next_es_min=10, next_es_max=10)  # always 10
    s = ProbeScheduler(cfg, random.Random(0))
    assert s.is_due(9) is False
    assert s.is_due(10) is True
    assert s.is_due(11) is False
