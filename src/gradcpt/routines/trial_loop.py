"""Per-block GradCPT trial loop (PsychoPy).

The loop is *frame-counted* — each transition lasts exactly ``transition_steps``
frames, with v-sync providing the timing. No clock-based scheduling.
"""
from __future__ import annotations

import random as _random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import numpy as np

from ..codebook import EventCode
from ..responses import KeyPressLog, KeyPressRecord, provisional_assign
from ..sequencing import TrialPlan
from ..transitions import TransitionBuffer

if TYPE_CHECKING:  # pragma: no cover
    from psychopy import visual
    from psychopy.hardware import keyboard

    from ..triggers.base import TriggerSender


@dataclass
class TrialOnset:
    """Per-trial timing record captured during the loop."""

    trial_idx: int            # 1-based within block
    condition: str
    image_id: str
    onset_global_s: float     # win.flip() timestamp at frame 0 of this trial
    n_frames: int             # transition_steps
    n_dropped: int            # frames whose interval exceeded refresh_threshold


def run_trial_loop(
    win: "visual.Window",
    kb: "keyboard.Keyboard",
    sender: "TriggerSender",
    *,
    plan: Sequence[TrialPlan],
    image_array_by_id: dict[str, np.ndarray],
    transition_steps: int,
    block_idx: int,
    dom_key: str,
    nondom_key: str,
    log_extra_keys: bool,
    unambig_low: float,
    unambig_high: float,
    image_size_px: int,
    image_stim,
    refresh_threshold_s: float,
    keypress_log: KeyPressLog,
    on_probe_due,                     # callable(trial_idx) -> None
    is_probe_due,                     # callable(trial_idx) -> bool
) -> list[TrialOnset]:
    """Run one block of GradCPT trials.

    Each trial is exactly ``transition_steps`` frames; the i-th frame shows
    ``linspace(prev_image, curr_image, transition_steps)[i]``. The first trial
    fades in from gray.

    The loop:
      * pre-allocates a :class:`TransitionBuffer` and primes it with
        gray → image[0] for trial 1, then computes image[0] → image[1] during
        trial 1's frames.
      * sends ``TRIAL_ONSET_*`` triggers via ``win.callOnFlip`` so they are
        synchronous with vertical retrace.
      * polls the keyboard once per frame; each press is logged to
        ``keypress_log`` with full provenance.
      * checks ``is_probe_due(trial_idx)`` at the end of each trial; if true,
        invokes ``on_probe_due(trial_idx)`` and primes the buffer with
        gray → image[next] before resuming.
    """
    h, w = image_size_px, image_size_px
    buf = TransitionBuffer(steps=transition_steps, h=h, w=w)
    gray = np.zeros((h, w), dtype=np.float32)

    # Prime: gray → image[0]
    arr0 = image_array_by_id[plan[0].image_id]
    buf.prime(gray, arr0)
    n_trials = len(plan)
    onsets: list[TrialOnset] = []

    for trial_pos in range(n_trials):
        plan_t = plan[trial_pos]
        trial_idx = trial_pos + 1
        # Reset frame intervals so per-trial dropped counts are isolated
        win.frameIntervals = []
        kb.clearEvents()

        # Schedule TRIAL_ONSET trigger at frame 0
        if plan_t.condition == "dom":
            event_code = EventCode.TRIAL_ONSET_DOM
        elif plan_t.condition == "nondom":
            event_code = EventCode.TRIAL_ONSET_NONDOM
        else:
            event_code = EventCode.TRIAL_ONSET_SCRAMBLED
        win.callOnFlip(sender.send, event_code, label=f"trial={trial_idx}")

        onset_t: float | None = None
        for frame_idx in range(transition_steps):
            image_stim.image = buf.frame(frame_idx)
            image_stim.draw()
            flip_t = win.flip()
            if frame_idx == 0:
                onset_t = flip_t

            # Poll keyboard
            keys = kb.getKeys(
                keyList=[dom_key, nondom_key] if log_extra_keys else [dom_key],
                waitRelease=False,
                clear=False,
            )
            for k in keys:
                _log_keypress(
                    kp_log=keypress_log,
                    key_event=k,
                    block_idx=block_idx,
                    trial_idx=trial_idx,
                    plan_t=plan_t,
                    frame_idx=frame_idx,
                    transition_steps=transition_steps,
                    onset_t=onset_t,
                    flip_t=flip_t,
                    dom_key=dom_key,
                    unambig_low=unambig_low,
                    unambig_high=unambig_high,
                    sender=sender,
                    win=win,
                )
            kb.clearEvents()

            # Generate the NEXT trial's transition during *this* trial's playback
            if frame_idx == 1 and trial_pos + 1 < n_trials:
                next_arr = image_array_by_id[plan[trial_pos + 1].image_id]
                buf.advance(next_arr)

        # Tally drops for this trial
        n_dropped = int(np.sum(np.asarray(win.frameIntervals) > refresh_threshold_s))
        onsets.append(
            TrialOnset(
                trial_idx=trial_idx,
                condition=plan_t.condition,
                image_id=plan_t.image_id,
                onset_global_s=onset_t if onset_t is not None else 0.0,
                n_frames=transition_steps,
                n_dropped=n_dropped,
            )
        )

        # If a probe is due, run it then re-prime gray → next trial's image
        if is_probe_due(trial_idx):
            on_probe_due(trial_idx)
            if trial_pos + 1 < n_trials:
                buf.prime(gray, image_array_by_id[plan[trial_pos + 1].image_id])

    return onsets


def _log_keypress(
    *,
    kp_log: KeyPressLog,
    key_event,
    block_idx: int,
    trial_idx: int,
    plan_t: TrialPlan,
    frame_idx: int,
    transition_steps: int,
    onset_t: float | None,
    flip_t: float,
    dom_key: str,
    unambig_low: float,
    unambig_high: float,
    sender,
    win,
) -> None:
    coherence = (frame_idx + 1) / transition_steps
    rt = (key_event.tDown - onset_t) if onset_t is not None else 0.0
    assigned, kind = provisional_assign(
        coherence, current_trial=trial_idx, unambig_low=unambig_low, unambig_high=unambig_high
    )
    code = EventCode.RESPONSE_DOM_KEY if key_event.name == dom_key else EventCode.RESPONSE_NONDOM_KEY
    win.callOnFlip(sender.send, code, label=f"trial={trial_idx}")
    kp_log.append(
        KeyPressRecord(
            timestamp_global_s=float(key_event.tDown),
            timestamp_trial_relative_s=float(rt),
            block_idx=block_idx,
            trial_idx=trial_idx,
            trial_condition=plan_t.condition,
            image_id=plan_t.image_id,
            coherence_at_press=coherence,
            frame_idx_in_trial=frame_idx,
            key=key_event.name,
            provisional_assigned_trial=assigned,
            provisional_assignment_kind=kind,
            rt_to_press_s=float(rt),
        )
    )
