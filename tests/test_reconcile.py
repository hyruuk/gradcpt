"""Branch tests for the response-to-trial reconciliation algorithm.

Each test exercises one branch of ``reconcile``. The cases are chosen to
match the structure of the original ``response_assignment.r`` algorithm so
we can argue equivalence by inspection plus golden-fixture comparison.
"""
from __future__ import annotations

from gradcpt.reconcile import ResolvedTrial, reconcile
from gradcpt.responses import KeyPressRecord
from gradcpt.sequencing import TrialPlan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def kp(
    *,
    trial_idx: int,
    coherence: float,
    rt: float = 0.5,
    condition: str = "dom",
    key: str = "j",
    image_id: str = "img",
) -> KeyPressRecord:
    """Build a KeyPressRecord with sensible defaults for tests."""
    return KeyPressRecord(
        timestamp_global_s=10.0,
        timestamp_trial_relative_s=rt,
        block_idx=0,
        trial_idx=trial_idx,
        trial_condition=condition,
        image_id=image_id,
        coherence_at_press=coherence,
        frame_idx_in_trial=int(coherence * 48),
        key=key,
        provisional_assigned_trial=trial_idx,
        provisional_assignment_kind="placeholder",
        rt_to_press_s=rt,
    )


def plan(*conds: str) -> list[TrialPlan]:
    """Build a trial plan from a sequence of condition labels."""
    return [TrialPlan(condition=c, image_id=f"i{i}") for i, c in enumerate(conds, start=1)]


def trial(out: list[ResolvedTrial], idx: int) -> ResolvedTrial:
    return next(r for r in out if r.trial_idx == idx)


# ---------------------------------------------------------------------------
# Branch tests
# ---------------------------------------------------------------------------


def test_unambig_low_assigns_to_previous_trial():
    out = reconcile(
        plan("dom", "dom", "dom", "dom", "dom"),
        [kp(trial_idx=4, coherence=0.3, rt=0.2)],
    )
    assert trial(out, 3).response_key == "j"  # press at trial 4 with low coherence → trial 3
    assert trial(out, 4).response_key is None
    # Reassigned-back: rt gains transition_time
    assert abs(trial(out, 3).rt_s - (0.2 + 0.8)) < 1e-9
    assert trial(out, 3).reassigned is True
    assert trial(out, 3).accuracy == 1


def test_unambig_high_assigns_to_current_trial():
    out = reconcile(
        plan("dom", "dom", "dom", "dom", "dom"),
        [kp(trial_idx=4, coherence=0.7, rt=0.7)],
    )
    assert trial(out, 4).response_key == "j"
    assert trial(out, 4).rt_s == 0.7
    assert trial(out, 4).reassigned is False
    assert trial(out, 4).accuracy == 1


def test_ambiguous_with_only_previous_already_assigned_goes_to_current():
    """If the previous trial already has a press, ambiguous goes to current."""
    out = reconcile(
        plan("dom", "dom", "dom", "dom", "dom"),
        [
            kp(trial_idx=3, coherence=0.7, rt=0.6),  # claims trial 3
            kp(trial_idx=4, coherence=0.5, rt=0.5),  # ambiguous on trial 4 → current (4)
        ],
    )
    assert trial(out, 3).response_key == "j"
    assert trial(out, 4).response_key == "j"


def test_ambiguous_with_only_current_already_assigned_goes_to_previous():
    """If the current trial already has a press, ambiguous goes to previous."""
    out = reconcile(
        plan("dom", "dom", "dom", "dom", "dom"),
        [
            kp(trial_idx=4, coherence=0.7, rt=0.7),  # claims trial 4
            kp(trial_idx=4, coherence=0.5, rt=0.5),  # ambiguous on trial 4 → previous (3)
        ],
    )
    assert trial(out, 3).response_key == "j"
    assert trial(out, 4).response_key == "j"


def test_ambiguous_neither_neighbor_assigned_dom_goes_to_current():
    out = reconcile(
        plan("dom", "dom", "dom", "dom", "dom"),
        [kp(trial_idx=4, coherence=0.5, rt=0.5, condition="dom")],
    )
    assert trial(out, 4).response_key == "j"
    assert trial(out, 3).response_key is None


def test_ambiguous_neither_neighbor_assigned_nondom_goes_to_previous():
    """Benefit of doubt: nondom (no-go) ambiguous press is pushed back to prev."""
    out = reconcile(
        plan("dom", "dom", "dom", "nondom", "dom"),
        [kp(trial_idx=4, coherence=0.5, rt=0.5, condition="nondom")],
    )
    assert trial(out, 3).response_key == "j"
    assert trial(out, 4).response_key is None  # the nondom trial gets benefit of doubt
    # Trial 3 is dom + has press → correct
    assert trial(out, 3).accuracy == 1
    # Trial 4 is nondom + no press → correct
    assert trial(out, 4).accuracy == 1


def test_benefit_of_doubt_disabled_routes_to_current():
    out = reconcile(
        plan("dom", "dom", "dom", "nondom", "dom"),
        [kp(trial_idx=4, coherence=0.5, rt=0.5, condition="nondom")],
        benefit_of_doubt_for_nogo=False,
    )
    assert trial(out, 4).response_key == "j"  # press lands on nondom trial
    assert trial(out, 4).accuracy == 0  # commission error


def test_ambiguous_both_neighbors_assigned_dedupes_to_current():
    """When both neighbors already have presses, ambiguous lands on current
    (then dedupe keeps the fastest of multiple presses on the same trial)."""
    out = reconcile(
        plan("dom", "dom", "dom", "dom", "dom"),
        [
            kp(trial_idx=3, coherence=0.7, rt=0.6),  # claims 3
            kp(trial_idx=4, coherence=0.7, rt=0.7),  # claims 4
            kp(trial_idx=4, coherence=0.5, rt=0.4),  # ambiguous → current (4); dedupe with above
        ],
    )
    # Trial 4 keeps the fastest press (rt=0.4)
    assert trial(out, 4).rt_s == 0.4
    assert trial(out, 3).rt_s == 0.6


def test_multiple_presses_on_one_trial_keep_fastest():
    out = reconcile(
        plan("dom", "dom", "dom", "dom", "dom"),
        [
            kp(trial_idx=4, coherence=0.7, rt=0.7),
            kp(trial_idx=4, coherence=0.7, rt=0.3),  # faster
            kp(trial_idx=4, coherence=0.7, rt=0.5),
        ],
    )
    assert trial(out, 4).rt_s == 0.3


def test_no_response_nogo_correct():
    out = reconcile(plan("dom", "nondom", "dom"), [])
    assert trial(out, 2).response_key is None
    assert trial(out, 2).accuracy == 1  # correct rejection


def test_no_response_go_incorrect():
    out = reconcile(plan("dom", "dom", "dom"), [])
    assert all(t.accuracy == 0 for t in out)  # all misses


def test_rt_adjustment_only_for_previous_trial_reassignment():
    """RT adjustment is +transition_time_s only when the press lands on the
    previous trial (i.e. coherence < low), not when it lands on its native
    trial."""
    out = reconcile(
        plan("dom", "dom", "dom"),
        [
            kp(trial_idx=2, coherence=0.7, rt=0.5),  # native (no adjust)
            kp(trial_idx=3, coherence=0.3, rt=0.2),  # → trial 2... wait already claimed
        ],
        transition_time_s=0.8,
    )
    # The second press unambiguously goes to trial 2 (coherence < low).
    # But trial 2 already has the first press. Dedupe keeps the fastest.
    # Press 1 (rt=0.5) vs press 2 (rt_assigned = 0.2 + 0.8 = 1.0 after adjust).
    # The dedupe step compares raw rt_to_press_s before adjustment — the
    # FASTEST raw press wins. Press 2 has rt 0.2 raw, which is faster.
    # After dedupe the kept press is press 2; its rt is then adjusted +0.8.
    assert trial(out, 2).response_key == "j"
    # The kept press is press 2 (raw rt=0.2). Reassigned-to-previous → +0.8.
    assert trial(out, 2).rt_s == 0.2 + 0.8
    assert trial(out, 2).reassigned is True


def test_ambiguous_flag_set_correctly():
    out = reconcile(
        plan("dom", "dom", "dom"),
        [
            kp(trial_idx=2, coherence=0.5, rt=0.5),  # ambiguous
            kp(trial_idx=3, coherence=0.7, rt=0.7),  # unambiguous current
        ],
    )
    # Trial 2 received an ambiguous press
    assert trial(out, 2).ambiguous is True
    # Trial 3 received an unambiguous press
    assert trial(out, 3).ambiguous is False


def test_resolved_trial_idx_is_one_indexed_and_complete():
    """Every trial in the plan appears in the output at the right position."""
    out = reconcile(plan("dom", "nondom", "dom", "dom"), [])
    assert [t.trial_idx for t in out] == [1, 2, 3, 4]
    assert [t.condition for t in out] == ["dom", "nondom", "dom", "dom"]
