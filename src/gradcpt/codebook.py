"""Trigger event codes.

Stable numeric codes are emitted by the trigger backends and recorded in BIDS
sidecars so analysts can map them back to event types.
"""
from __future__ import annotations

from enum import IntEnum


class EventCode(IntEnum):
    EXPERIMENT_START = 1
    EXPERIMENT_END = 2

    BLOCK_START = 10
    BLOCK_END = 11

    TRIAL_ONSET_DOM = 20
    TRIAL_ONSET_NONDOM = 21
    TRIAL_ONSET_SCRAMBLED = 22

    RESPONSE_DOM_KEY = 30
    RESPONSE_NONDOM_KEY = 31

    PROBE_START = 40
    PROBE_END = 41

    PROBE_ITEM_ONSET = 50
    PROBE_ITEM_RESPONSE = 51
    PROBE_ITEM_SUBMIT = 52


CODEBOOK_VERSION = "1"


def codebook_dict() -> dict[str, int]:
    """Return the full codebook as {name: int}, suitable for JSON dumping."""
    return {c.name: int(c) for c in EventCode}


def code_levels() -> dict[str, str]:
    """Return BIDS-style ``{name: description}`` mapping for the events.json sidecar."""
    return {
        "EXPERIMENT_START": "Experiment-level start marker.",
        "EXPERIMENT_END": "Experiment-level end marker.",
        "BLOCK_START": "Start of a block of GradCPT trials.",
        "BLOCK_END": "End of a block of GradCPT trials.",
        "TRIAL_ONSET_DOM": "Onset (frame 0) of a dominant-category (city / go) trial.",
        "TRIAL_ONSET_NONDOM": "Onset (frame 0) of a non-dominant (mountain / no-go) trial.",
        "TRIAL_ONSET_SCRAMBLED": "Onset of a scrambled-scene trial (when scrambled is enabled).",
        "RESPONSE_DOM_KEY": "Keyboard press of the dominant-response key during the task.",
        "RESPONSE_NONDOM_KEY": "Keyboard press of the non-dominant-response key (commission error).",
        "PROBE_START": "Start of an experience-sampling probe.",
        "PROBE_END": "End of an experience-sampling probe.",
        "PROBE_ITEM_ONSET": "A single experience-sampling slider item is shown.",
        "PROBE_ITEM_RESPONSE": "First slider movement on a probe item (rating registered).",
        "PROBE_ITEM_SUBMIT": "Submit (Enter) pressed for a probe item.",
    }
