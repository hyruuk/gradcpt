"""Offline response-to-trial reconciliation.

Pure-Python port of ``gradcptpy/process_data/response_assignment.r``. Given a
trial plan and a raw keypress log, produces one resolved row per trial with
final accuracy, RT, and ambiguity flags.

The original R algorithm is documented at the top of the source file; this
implementation preserves its semantics exactly. Equivalence is enforced by
``tests/test_reconcile.py`` and ``tests/test_reconcile_golden.py``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from .responses import KeyPressRecord
from .sequencing import TrialPlan


@dataclass
class ResolvedTrial:
    """One row in the reconciled trial table."""

    trial_idx: int            # 1-based trial number within block
    condition: str
    image_id: str
    response_key: str | None
    rt_s: float | None
    accuracy: int             # 1 = correct, 0 = error
    ambiguous: bool           # press required ambiguous-band resolution
    reassigned: bool          # press was reassigned to a non-natural trial


# Symbolic placeholder for "not yet decided" in the candidate map.
_AMBIG = "AMBIG"


def reconcile(
    trial_plan: Sequence[TrialPlan],
    keypresses: Sequence[KeyPressRecord],
    *,
    unambig_low: float = 0.4,
    unambig_high: float = 0.55,
    transition_time_s: float = 0.8,
    benefit_of_doubt_for_nogo: bool = True,
) -> list[ResolvedTrial]:
    """Map raw keypresses to trials and compute accuracy.

    Trial indices in :class:`KeyPressRecord` and the returned
    :class:`ResolvedTrial` are 1-based and refer to position within the block.

    The four-pass algorithm:

    1. Classify each press as ``previous`` / ``current`` / ``ambiguous`` from
       coherence vs. ``unambig_low`` / ``unambig_high``.
    2. Resolve ambiguous presses using context: prefer an unassigned neighbor;
       if neither neighbor is assigned, use ``benefit_of_doubt_for_nogo`` to
       decide.
    3. Deduplicate — if multiple presses landed on the same trial, keep the
       fastest by ``rt_to_press_s``.
    4. Build the per-trial output and code accuracy: dom + press = correct,
       nondom + no-press = correct, else incorrect. RTs that were reassigned
       to the *previous* trial gain ``transition_time_s`` (since the press
       was timed against the original trial onset).
    """
    n_presses = len(keypresses)

    # Pass 1 — preliminary classification per press
    cand: list[int | str] = [0] * n_presses
    for i, kp in enumerate(keypresses):
        if kp.coherence_at_press < unambig_low:
            cand[i] = kp.trial_idx - 1
        elif kp.coherence_at_press > unambig_high:
            cand[i] = kp.trial_idx
        else:
            cand[i] = _AMBIG

    # Pass 2 — resolve ambiguous presses
    # We need the *current* state of which trials are already claimed; we
    # iterate until no more ambiguous presses change. In practice one pass
    # is enough because each press only consults its own neighbors and the
    # disambiguation never makes another press ambiguous, but we follow the
    # R algorithm's order-dependent semantics by walking presses in order.
    for i, kp in enumerate(keypresses):
        if cand[i] != _AMBIG:
            continue
        t = kp.trial_idx
        prev_assigned = any(cand[j] == t - 1 for j in range(n_presses) if j != i)
        curr_assigned = any(cand[j] == t for j in range(n_presses) if j != i)
        if prev_assigned and not curr_assigned:
            cand[i] = t
        elif curr_assigned and not prev_assigned:
            cand[i] = t - 1
        elif not prev_assigned and not curr_assigned:
            if benefit_of_doubt_for_nogo and kp.trial_condition == "nondom":
                cand[i] = t - 1
            else:
                cand[i] = t
        else:
            # Both neighbors taken — assign to current; will be deduped below.
            cand[i] = t

    # Pass 3 — dedupe: per assigned trial, keep the fastest press
    by_trial: dict[int, list[tuple[int, KeyPressRecord]]] = defaultdict(list)
    for i, kp in enumerate(keypresses):
        by_trial[int(cand[i])].append((i, kp))
    chosen_idx: dict[int, int] = {}
    for tid, items in by_trial.items():
        items.sort(key=lambda t: t[1].rt_to_press_s)
        chosen_idx[tid] = items[0][0]

    # Pass 4 — build ResolvedTrial list
    resolved: list[ResolvedTrial] = []
    for trial_pos, plan in enumerate(trial_plan, start=1):
        idx = chosen_idx.get(trial_pos)
        if idx is None:
            response_key = None
            rt: float | None = None
            ambiguous = False
            reassigned = False
        else:
            kp = keypresses[idx]
            response_key = kp.key
            rt = kp.rt_to_press_s
            ambiguous = kp.coherence_at_press >= unambig_low and kp.coherence_at_press <= unambig_high
            reassigned = kp.trial_idx != trial_pos
            # If the press was reassigned to the PREVIOUS trial, compensate
            # the RT by the inter-trial transition duration (mirrors R's
            # `0.8 + rt` adjustment).
            if reassigned and trial_pos == kp.trial_idx - 1:
                rt = rt + transition_time_s

        if plan.condition == "dom":
            accuracy = 1 if rt is not None else 0
        else:  # nondom (or scrambled used as nogo)
            accuracy = 1 if rt is None else 0

        resolved.append(
            ResolvedTrial(
                trial_idx=trial_pos,
                condition=plan.condition,
                image_id=plan.image_id,
                response_key=response_key,
                rt_s=rt,
                accuracy=accuracy,
                ambiguous=ambiguous,
                reassigned=reassigned,
            )
        )

    return resolved
