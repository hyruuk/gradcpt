"""Refresh-rate measurement and frame-budget math.

PsychoPy is imported lazily inside the measurement function so the rest of
the module is importable without it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from psychopy import visual  # noqa: F401


log = logging.getLogger(__name__)


class TimingError(RuntimeError):
    """Raised when measured timing differs from expected beyond abort tolerance."""


@dataclass(frozen=True)
class RefreshRateMeasurement:
    measured_hz: float
    expected_hz: float | None
    deviation_hz: float | None
    n_warmup_frames: int
    n_frames_used: int


def compute_transition_steps(measured_hz: float, transition_time_s: float) -> int:
    """Number of frames to fade from one image to the next.

    Always at least 2 (a transition with one frame is just a swap).
    """
    if measured_hz <= 0:
        raise ValueError("measured_hz must be > 0")
    if transition_time_s <= 0:
        raise ValueError("transition_time_s must be > 0")
    return max(2, round(measured_hz * transition_time_s))


def check_refresh_rate(
    meas: RefreshRateMeasurement,
    *,
    tolerance_hz: float,
    abort_tolerance_hz: float,
) -> None:
    """Warn or abort based on tolerance bands.

    If ``meas.expected_hz`` is ``None`` (no expected value declared) the
    check is skipped — we trust the measured rate. The same band logic is
    applied for both directions of deviation when expected is set.
    """
    if meas.expected_hz is None:
        log.info("Measured refresh rate %.2f Hz (no expected value to compare).", meas.measured_hz)
        return
    dev = abs(meas.measured_hz - meas.expected_hz)
    if dev > abort_tolerance_hz:
        raise TimingError(
            f"Measured refresh rate {meas.measured_hz:.2f} Hz deviates from "
            f"expected {meas.expected_hz:.2f} Hz by {dev:.2f} Hz "
            f"(>{abort_tolerance_hz}). Aborting."
        )
    if dev > tolerance_hz:
        log.warning(
            "Refresh-rate deviation %.2f Hz (measured=%.2f, expected=%.2f); "
            "tolerated but inspect post-hoc.",
            dev,
            meas.measured_hz,
            meas.expected_hz,
        )


def measure_refresh_rate(
    win,
    expected_hz: float | None,
    *,
    n_identical: int = 10,
    n_max_frames: int = 100,
    n_warmup: int = 10,
    threshold_ms: float = 1.0,
) -> RefreshRateMeasurement:
    """Measure the active monitor's refresh rate.

    Uses :meth:`psychopy.visual.Window.getActualFrameRate` which waits for
    ``n_identical`` consecutive vsync flips that fall within ``threshold_ms``
    of each other before returning. Falls back to the median of N flip
    intervals if that returns ``None``.
    """
    measured = win.getActualFrameRate(
        nIdentical=n_identical,
        nMaxFrames=n_max_frames,
        nWarmUpFrames=n_warmup,
        threshold=threshold_ms,
    )
    n_used = n_max_frames
    if measured is None:
        measured = _fallback_median_rate(win, n_warmup=n_warmup, n_frames=30)
        n_used = 30
    dev = None if expected_hz is None else abs(measured - expected_hz)
    return RefreshRateMeasurement(
        measured_hz=float(measured),
        expected_hz=float(expected_hz) if expected_hz is not None else None,
        deviation_hz=float(dev) if dev is not None else None,
        n_warmup_frames=n_warmup,
        n_frames_used=n_used,
    )


def _fallback_median_rate(win, *, n_warmup: int, n_frames: int) -> float:
    from psychopy import core  # imported lazily

    clock = core.Clock()
    for _ in range(n_warmup):
        win.flip()
    intervals: list[float] = []
    last = clock.getTime()
    for _ in range(n_frames):
        win.flip()
        now = clock.getTime()
        intervals.append(now - last)
        last = now
    return float(1.0 / np.median(intervals))


def summarize_frames(frame_intervals: list[float], threshold_s: float) -> dict[str, float | int]:
    """Summarize a block's recorded frame intervals.

    Returns a dict with n_frames, n_dropped, mean_interval_ms, max_interval_ms.
    Designed to be JSON-serializable.
    """
    arr = np.asarray(frame_intervals, dtype=float)
    if arr.size == 0:
        return {"n_frames": 0, "n_dropped": 0, "mean_interval_ms": 0.0, "max_interval_ms": 0.0}
    n_dropped = int(np.sum(arr > threshold_s))
    return {
        "n_frames": int(arr.size),
        "n_dropped": n_dropped,
        "mean_interval_ms": float(arr.mean() * 1000.0),
        "max_interval_ms": float(arr.max() * 1000.0),
    }
