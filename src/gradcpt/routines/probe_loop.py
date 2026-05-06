"""Render an experience-sampling probe (PsychoPy)."""
from __future__ import annotations

import random as _random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..codebook import EventCode
from ..config import ProbeConfig
from ..probes import ProbeItem, order_items_for_probe

if TYPE_CHECKING:  # pragma: no cover
    from psychopy import visual
    from psychopy.event import Mouse
    from psychopy.hardware import keyboard

    from ..triggers.base import TriggerSender


@dataclass
class ProbeItemRecord:
    item_name: str
    onset_s: float
    response: float | None
    rt_slider_s: float | None
    rt_submit_s: float | None


def run_probe(
    win: "visual.Window",
    kb: "keyboard.Keyboard",
    mouse: "Mouse",
    sender: "TriggerSender",
    cfg: ProbeConfig,
    items: list[ProbeItem],
    rng: _random.Random,
    *,
    probe_id: int,
) -> list[ProbeItemRecord]:
    """Run one probe (a sequence of slider items). Returns per-item records."""
    win.callOnFlip(sender.send, EventCode.PROBE_START, label=f"probe={probe_id}")
    win.flip()
    out: list[ProbeItemRecord] = []
    ordered = order_items_for_probe(items, rng)
    for item_idx, item in enumerate(ordered):
        rec = _run_probe_item(win, kb, mouse, sender, cfg, item, rng, probe_id=probe_id)
        out.append(rec)
        if cfg.isi_s > 0:
            _run_isi(win, cfg.isi_s)
    win.callOnFlip(sender.send, EventCode.PROBE_END, label=f"probe={probe_id}")
    win.flip()
    return out


def _run_probe_item(
    win, kb, mouse, sender, cfg: ProbeConfig, item: ProbeItem, rng: _random.Random, *, probe_id: int
) -> ProbeItemRecord:
    from psychopy import visual

    slider = visual.Slider(
        win=win,
        ticks=(0, 1),
        granularity=0.0,
        size=(0.8, 0.05),
        pos=(0, -0.1),
        labels=None,
        style="rating",
    )
    text = visual.TextStim(win=win, text=item.text, pos=(0, 0.25), wrapWidth=1.5, color=(1, 1, 1))
    low = visual.TextStim(win=win, text=item.low_anchor, pos=(-0.5, -0.25), color=(1, 1, 1))
    high = visual.TextStim(win=win, text=item.high_anchor, pos=(0.5, -0.25), color=(1, 1, 1))
    enter_prompt = visual.TextStim(
        win=win, text='Press "Enter" to advance.', pos=(0, -0.5), color=(0.6, 0.6, 0.6)
    )

    jitter_x = rng.uniform(-cfg.initial_mouse_jitter, cfg.initial_mouse_jitter)
    mouse.setPos((jitter_x, cfg.initial_mouse_y))
    win.mouseVisible = True

    win.callOnFlip(sender.send, EventCode.PROBE_ITEM_ONSET, label=item.name)
    onset_t = win.flip()
    kb.clearEvents()

    slider_response_t: float | None = None
    submit_t: float | None = None

    while submit_t is None:
        slider.draw()
        text.draw()
        low.draw()
        high.draw()
        if slider.rating is not None:
            enter_prompt.draw()
            if slider_response_t is None:
                slider_response_t = win.flip()
                win.callOnFlip(sender.send, EventCode.PROBE_ITEM_RESPONSE, label=item.name)
            else:
                win.flip()
            keys = kb.getKeys(keyList=[cfg.submit_key], waitRelease=False, clear=True)
            if keys:
                submit_t = keys[0].tDown
                win.callOnFlip(sender.send, EventCode.PROBE_ITEM_SUBMIT, label=item.name)
        else:
            win.flip()

    win.mouseVisible = False
    rt_slider = (slider_response_t - onset_t) if slider_response_t is not None else None
    rt_submit = (submit_t - slider_response_t) if slider_response_t is not None else None
    return ProbeItemRecord(
        item_name=item.name,
        onset_s=onset_t,
        response=slider.rating,
        rt_slider_s=rt_slider,
        rt_submit_s=rt_submit,
    )


def _run_isi(win, isi_s: float) -> None:
    from psychopy import core

    end = core.getTime() + isi_s
    while core.getTime() < end:
        win.flip()
