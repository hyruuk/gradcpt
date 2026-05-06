"""Top-level orchestrator: opens window, runs blocks, writes BIDS output."""
from __future__ import annotations

import logging
import random as _random
import signal
from typing import TYPE_CHECKING, Optional

from . import __version__ as PACKAGE_VERSION
from .bids import BIDSWriter, EventRow
from .codebook import EventCode
from .config import Config
from .errors import ExperimentInterrupted
from .probes import ProbeScheduler, load_probe_items
from .reconcile import reconcile
from .responses import KeyPressLog
from .sequencing import generate_sequence
from .stimuli import load_category
from .timing import (
    check_refresh_rate,
    compute_transition_steps,
    measure_refresh_rate,
    summarize_frames,
)
from .triggers import make_sender

if TYPE_CHECKING:  # pragma: no cover
    from psychopy import visual
    from psychopy.event import Mouse
    from psychopy.hardware import keyboard

    from .triggers.base import TriggerSender

log = logging.getLogger(__name__)


def run_experiment(
    cfg: Config,
    *,
    win: Optional["visual.Window"] = None,
    kb: Optional["keyboard.Keyboard"] = None,
    mouse: Optional["Mouse"] = None,
    sender: Optional["TriggerSender"] = None,
) -> None:
    """Run the full experiment.

    Args
    ----
    cfg : validated configuration
    win, kb, mouse, sender : optional injection points for testing or for
        running with a pre-built window. ``None`` triggers default construction.
    """
    cfg.validate()

    rng = _random.Random(cfg.task.seed)

    # Resolve dom_key (auto = randomly j or f per session)
    if cfg.task.dom_key == "auto":
        dom_key = rng.choice(["j", "f"])
    else:
        dom_key = cfg.task.dom_key
    nondom_key = "f" if dom_key == "j" else "j"

    # Stimuli — load each enabled category. Category folder names (city,
    # mountain, scrambled) are conventional and not currently configurable.
    dom_ids, dom_arrays = load_category(cfg.stimuli, "city")
    nondom_ids, nondom_arrays = load_category(cfg.stimuli, "mountain")
    image_array_by_id: dict = {}
    for i, a in zip(dom_ids, dom_arrays):
        image_array_by_id[i] = a
    for i, a in zip(nondom_ids, nondom_arrays):
        image_array_by_id[i] = a
    if cfg.stimuli.scrambled_enabled:
        scr_ids, scr_arrays = load_category(cfg.stimuli, "scrambled")
        for i, a in zip(scr_ids, scr_arrays):
            image_array_by_id[i] = a

    # PsychoPy setup (lazy import)
    from psychopy import core, event, visual
    from psychopy.hardware import keyboard

    # Restore Python's default SIGINT handler so Ctrl+C from the terminal
    # raises KeyboardInterrupt promptly. PsychoPy / pyglet sometimes
    # install their own handler that swallows it.
    try:
        signal.signal(signal.SIGINT, signal.default_int_handler)
    except ValueError:
        # Not on the main thread — leave the handler alone.
        pass

    if sender is None:
        sender = make_sender(cfg.triggers)
    if win is None:
        win = visual.Window(
            size=cfg.window.size,
            fullscr=cfg.window.fullscreen,
            screen=cfg.window.screen,
            monitor=cfg.window.monitor_name,
            color=cfg.window.color,
            units=cfg.window.units,
            waitBlanking=True,
            useFBO=True,
            allowGUI=False,
        )
    if kb is None:
        kb = keyboard.Keyboard(backend="ptb")
    if mouse is None:
        mouse = event.Mouse(visible=False, win=win)

    sender.open()
    sender.send(EventCode.EXPERIMENT_START, label=f"gradcpt v{PACKAGE_VERSION}")

    # Refresh-rate measurement
    meas = measure_refresh_rate(win, expected_hz=cfg.task.expected_refresh_rate_hz)
    check_refresh_rate(
        meas,
        tolerance_hz=cfg.task.refresh_rate_tolerance_hz,
        abort_tolerance_hz=cfg.task.refresh_rate_abort_tolerance_hz,
    )
    transition_steps = compute_transition_steps(meas.measured_hz, cfg.task.transition_time_s)
    refresh_threshold_s = 1.5 / meas.measured_hz
    win.refreshThreshold = refresh_threshold_s
    win.recordFrameIntervals = cfg.window.record_frame_intervals
    log.info(
        "Refresh rate: measured=%.2f Hz, expected=%.2f Hz, transition_steps=%d",
        meas.measured_hz, cfg.task.expected_refresh_rate_hz, transition_steps,
    )

    # ImageStim — single instance reused for all trials.
    # `units="height"` makes the size square regardless of screen aspect
    # ratio (1.0 = full screen height in *both* axes). Without this, a
    # `units="norm"` size of (0.5, 0.5) on a 16:9 screen renders as a
    # horizontal ellipse.
    image_stim = visual.ImageStim(
        win=win,
        size=(cfg.stimuli.display_size, cfg.stimuli.display_size),
        pos=(0, 0),
        units="height",
    )

    # Probes
    probe_items = load_probe_items(cfg.probe.items_file) if cfg.probe.enabled else []

    # BIDS writer
    writer = BIDSWriter(cfg)

    # Welcome / instructions
    from .routines.instructions import (
        block_rest_screen,
        block_start_screen,
        countdown_screen,
        debrief_screen,
        welcome_screen,
    )
    from .routines.probe_loop import run_probe
    from .routines.trial_loop import run_trial_loop

    interrupted = False
    try:
        welcome_screen(win, kb, dom_key=dom_key)
        _run_blocks_inner(
            cfg=cfg,
            win=win,
            kb=kb,
            mouse=mouse,
            sender=sender,
            writer=writer,
            rng=rng,
            dom_key=dom_key,
            nondom_key=nondom_key,
            transition_steps=transition_steps,
            refresh_threshold_s=refresh_threshold_s,
            image_stim=image_stim,
            image_array_by_id=image_array_by_id,
            dom_ids=dom_ids,
            nondom_ids=nondom_ids,
            probe_items=probe_items,
            meas=meas,
        )
    except (ExperimentInterrupted, KeyboardInterrupt) as e:
        log.warning("Experiment interrupted: %s", e or "(no message)")
        interrupted = True
    finally:
        try:
            sender.send(EventCode.EXPERIMENT_END)
        except Exception:
            pass
        try:
            sender.close()
        except Exception:
            pass
        # If we were interrupted mid-block, flush whatever we have.
        try:
            if writer._current_run_idx is not None:
                writer.set_block_metadata(dom_key=dom_key, seed=cfg.task.seed)
                writer.end_block()
        except Exception as e:
            log.warning("Could not flush partial block: %s", e)
        try:
            writer.finalize()
        except Exception as e:
            log.warning("Could not finalize BIDS dataset: %s", e)
        if not interrupted:
            try:
                writer.sanity_check()
            except Exception as e:
                log.warning("BIDS sanity check failed: %s", e)
            try:
                debrief_screen(win, kb)
            except Exception:
                pass
        try:
            win.close()
        except Exception:
            pass


def _run_blocks_inner(
    *,
    cfg: Config,
    win,
    kb,
    mouse,
    sender,
    writer: BIDSWriter,
    rng: _random.Random,
    dom_key: str,
    nondom_key: str,
    transition_steps: int,
    refresh_threshold_s: float,
    image_stim,
    image_array_by_id: dict,
    dom_ids: list[str],
    nondom_ids: list[str],
    probe_items,
    meas,
) -> None:
    """Inner loop over blocks. Split out so the runner can wrap it in a
    single try/finally for graceful interruption handling."""
    from psychopy import core

    from .routines.instructions import block_rest_screen, block_start_screen, countdown_screen
    from .routines.probe_loop import run_probe
    from .routines.trial_loop import run_trial_loop

    for block_idx in range(cfg.task.n_blocks):
        run_idx = writer.begin_block(block_idx)
        log.info("Beginning block %d (BIDS run-%02d)", block_idx, run_idx)
        block_start_screen(win, kb, dom_key=dom_key, block_idx=block_idx)
        countdown_screen(win, seconds=5)

        plan = generate_sequence(
            n_trials=cfg.task.n_trials,
            prop_dom=cfg.task.prop_dom,
            dom_image_ids=dom_ids,
            nondom_image_ids=nondom_ids,
            rng=rng,
        )

        # Block-start event
        block_clock = core.Clock()
        block_clock.reset()
        sender.send(EventCode.BLOCK_START, label=f"block={block_idx}")
        writer.append_event(
            EventRow(onset=0.0, duration=0.0, trial_type="block_start", block_idx=block_idx)
        )

        keypress_log = KeyPressLog()
        win.frameIntervals = []  # cleared per-trial inside run_trial_loop too

        scheduler = ProbeScheduler(cfg.probe, rng=rng)
        probes_ran: list[int] = []

        def _on_probe_due(trial_idx: int) -> None:
            probe_id = len(probes_ran) + 1
            probes_ran.append(probe_id)
            records = run_probe(
                win, kb, mouse, sender, cfg.probe, probe_items, rng, probe_id=probe_id
            )
            now = block_clock.getTime()
            writer.append_event(
                EventRow(
                    onset=now,
                    duration=0.0,
                    trial_type="probe_start",
                    probe_id=probe_id,
                    block_idx=block_idx,
                )
            )
            for r in records:
                writer.append_event(
                    EventRow(
                        onset=r.onset_s - block_clock.getTime() + now,
                        duration=(r.rt_slider_s or 0.0) + (r.rt_submit_s or 0.0),
                        trial_type="probe_item",
                        probe_id=probe_id,
                        item_name=r.item_name,
                        item_response=r.response,
                        block_idx=block_idx,
                    )
                )
            writer.append_event(
                EventRow(
                    onset=block_clock.getTime(),
                    duration=0.0,
                    trial_type="probe_end",
                    probe_id=probe_id,
                    block_idx=block_idx,
                )
            )
            scheduler.advance(trial_idx)

        onsets = run_trial_loop(
            win,
            kb,
            sender,
            plan=plan,
            image_array_by_id=image_array_by_id,
            transition_steps=transition_steps,
            block_idx=block_idx,
            dom_key=dom_key,
            nondom_key=nondom_key,
            log_extra_keys=cfg.task.log_extra_keys,
            unambig_low=cfg.task.unambig_low,
            unambig_high=cfg.task.unambig_high,
            image_size_px=cfg.stimuli.image_size_px,
            image_stim=image_stim,
            refresh_threshold_s=refresh_threshold_s,
            keypress_log=keypress_log,
            on_probe_due=_on_probe_due,
            is_probe_due=scheduler.is_due,
        )

        # Reconcile keypresses → trial table
        resolved = reconcile(
            list(plan),
            list(keypress_log),
            unambig_low=cfg.task.unambig_low,
            unambig_high=cfg.task.unambig_high,
            transition_time_s=cfg.task.transition_time_s,
            benefit_of_doubt_for_nogo=cfg.task.benefit_of_doubt_for_nogo,
        )

        # Append per-trial rows to events.tsv (relative onsets)
        block_origin = onsets[0].onset_global_s if onsets else 0.0
        n_dropped_by_trial = {o.trial_idx: o.n_dropped for o in onsets}
        for r in resolved:
            o = next((x for x in onsets if x.trial_idx == r.trial_idx), None)
            onset_rel = (o.onset_global_s - block_origin) if o else 0.0
            writer.append_resolved_trial(
                r,
                onset=onset_rel,
                duration=cfg.task.transition_time_s,
                n_dropped=n_dropped_by_trial.get(r.trial_idx, 0),
            )

        # Per-press raw log → BIDS beh.tsv
        for kp_record in keypress_log:
            writer.append_keypress(kp_record)

        # Block-end event
        sender.send(EventCode.BLOCK_END, label=f"block={block_idx}")
        writer.append_event(
            EventRow(
                onset=block_clock.getTime(),
                duration=0.0,
                trial_type="block_end",
                block_idx=block_idx,
            )
        )

        # Block metadata for the BIDS sidecar
        frame_summary = summarize_frames(list(win.frameIntervals), threshold_s=refresh_threshold_s)
        writer.set_block_metadata(
            frame_summary=frame_summary,
            refresh_meas={
                "measured_hz": meas.measured_hz,
                "expected_hz": meas.expected_hz,
                "deviation_hz": meas.deviation_hz,
            },
            dom_key=dom_key,
            seed=cfg.task.seed,
        )
        writer.end_block()
        block_rest_screen(win, kb, block_idx=block_idx)
