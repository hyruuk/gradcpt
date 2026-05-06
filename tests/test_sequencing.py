from __future__ import annotations

import random

import pytest

from gradcpt.sequencing import SequencingError, TrialPlan, generate_sequence


DOM5 = ["d0", "d1", "d2", "d3", "d4"]
NDM5 = ["n0", "n1", "n2", "n3", "n4"]


def test_proportions_exact_default_80_10():
    seq = generate_sequence(80, 0.9, DOM5, NDM5, rng=random.Random(0))
    assert sum(t.condition == "dom" for t in seq) == 72
    assert sum(t.condition == "nondom" for t in seq) == 8
    assert len(seq) == 80


def test_no_consecutive_identical_images():
    seq = generate_sequence(
        500, 0.9, [f"d{i}" for i in range(10)], [f"n{i}" for i in range(10)], rng=random.Random(1)
    )
    for a, b in zip(seq, seq[1:]):
        assert a.image_id != b.image_id, f"Repeat at {a} -> {b}"


def test_deterministic_with_same_seed():
    s1 = generate_sequence(80, 0.9, DOM5, NDM5, rng=random.Random(42))
    s2 = generate_sequence(80, 0.9, DOM5, NDM5, rng=random.Random(42))
    assert s1 == s2


def test_different_seeds_produce_different_sequences():
    s1 = generate_sequence(80, 0.9, DOM5, NDM5, rng=random.Random(1))
    s2 = generate_sequence(80, 0.9, DOM5, NDM5, rng=random.Random(2))
    assert s1 != s2


def test_n_dom_rounding_81_trials():
    # 81 * 0.9 = 72.9 → round() = 73 (banker's rounding gives 73 for .9 suffix)
    seq = generate_sequence(81, 0.9, DOM5, NDM5, rng=random.Random(0))
    n_dom = sum(t.condition == "dom" for t in seq)
    assert n_dom == 73
    assert len(seq) == 81


def test_singleton_dom_pool_with_multiple_dom_trials_raises():
    with pytest.raises(SequencingError, match="dom pool"):
        generate_sequence(10, 0.9, ["only"], NDM5, rng=random.Random(0))


def test_singleton_nondom_pool_with_multiple_nondom_trials_raises():
    with pytest.raises(SequencingError, match="nondom pool"):
        generate_sequence(20, 0.5, DOM5, ["only"], rng=random.Random(0))


def test_empty_dom_pool_with_dom_trials_raises():
    with pytest.raises(SequencingError, match="dom_image_ids is empty"):
        generate_sequence(10, 0.9, [], NDM5, rng=random.Random(0))


def test_n_trials_zero_raises():
    with pytest.raises(SequencingError, match="n_trials"):
        generate_sequence(0, 0.9, DOM5, NDM5, rng=random.Random(0))


def test_prop_dom_out_of_range_raises():
    with pytest.raises(SequencingError, match="prop_dom"):
        generate_sequence(10, 1.5, DOM5, NDM5, rng=random.Random(0))


def test_returned_items_are_trial_plan_namedtuples():
    seq = generate_sequence(5, 0.6, DOM5, NDM5, rng=random.Random(0))
    assert all(isinstance(t, TrialPlan) for t in seq)
    assert all(t.condition in {"dom", "nondom"} for t in seq)
