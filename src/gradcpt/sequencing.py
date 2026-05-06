"""Trial-sequence generation for GradCPT.

Generates a sequence of (condition, image_id) tuples honoring:
  * exactly ``round(n_trials * prop_dom)`` dominant trials and the rest non-dom
  * no two adjacent trials use the same image (regardless of category)
  * deterministic given a seeded :class:`random.Random`

Comparing image *IDs* (filename stems) rather than image arrays is faster and
equivalent — we control the ID-to-array mapping in ``stimuli.py``.
"""
from __future__ import annotations

import random as _random
from typing import NamedTuple, Sequence


class SequencingError(ValueError):
    """Raised when the sequence cannot be generated under the given constraints."""


class TrialPlan(NamedTuple):
    condition: str        # "dom" | "nondom" | "scrambled"
    image_id: str


def generate_sequence(
    n_trials: int,
    prop_dom: float,
    dom_image_ids: Sequence[str],
    nondom_image_ids: Sequence[str],
    *,
    rng: _random.Random,
) -> list[TrialPlan]:
    """Generate a 90/10 trial sequence with no consecutive identical images.

    Parameters
    ----------
    n_trials : number of trials to generate (>= 1).
    prop_dom : proportion of dominant trials (in (0, 1)).
    dom_image_ids, nondom_image_ids : pools of image identifiers.
    rng : seeded :class:`random.Random` for determinism.

    Raises
    ------
    SequencingError
        If the constraints can never be satisfied (empty pools when needed,
        or singleton pool with adjacent same-category trials).
    """
    if n_trials < 1:
        raise SequencingError("n_trials must be >= 1")
    if not 0 < prop_dom < 1:
        raise SequencingError("prop_dom must be in (0, 1)")

    n_dom = round(n_trials * prop_dom)
    n_nondom = n_trials - n_dom

    if n_dom > 0 and len(dom_image_ids) == 0:
        raise SequencingError("dom_image_ids is empty but n_dom > 0")
    if n_nondom > 0 and len(nondom_image_ids) == 0:
        raise SequencingError("nondom_image_ids is empty but n_nondom > 0")

    # Detect cases where the constraint is structurally unsolvable: a singleton
    # pool combined with two adjacent same-category trials would force a
    # repeat. We check the worst case (two same-category in a row) up front.
    if n_dom >= 2 and len(dom_image_ids) < 2:
        raise SequencingError(
            "dom pool has <2 unique images but n_dom >= 2 — adjacent dom trials must differ"
        )
    if n_nondom >= 2 and len(nondom_image_ids) < 2:
        raise SequencingError(
            "nondom pool has <2 unique images but n_nondom >= 2 — adjacent nondom trials must differ"
        )

    cats = ["dom"] * n_dom + ["nondom"] * n_nondom
    rng.shuffle(cats)

    out: list[TrialPlan] = []
    prev_id: str | None = None
    for cat in cats:
        pool = list(dom_image_ids if cat == "dom" else nondom_image_ids)
        if prev_id in pool and len(pool) > 1:
            pool.remove(prev_id)
        choice = rng.choice(pool)
        out.append(TrialPlan(cat, choice))
        prev_id = choice
    return out
