"""Transition generator.

Each trial of GradCPT walks ``transition_steps`` frames of a per-pixel
linear interpolation from the previous image to the current image.

This module owns one pre-allocated ``(steps, H, W)`` float32 buffer that's
overwritten in-place at each trial boundary. Earlier double-buffered designs
are tempting (overlap the next-trial compute with the current trial's
playback) but the buffer-swap semantics are easy to get wrong — see the
"flicker on frames 1+ of each trial" regression that we hit on the first
try. The vectorized fill below runs in a few milliseconds even at
default settings, well under one frame interval at 60–144 Hz, so a single
buffer with a fill at each trial boundary is plenty.

Memory at default (256×256, 48 steps, float32): ``48 × 256 × 256 × 4 B ≈ 12 MB``.
"""
from __future__ import annotations

import numpy as np


class TransitionBuffer:
    """Single pre-allocated float32 buffer of shape ``(steps, H, W)``.

    Usage::

        buf = TransitionBuffer(steps=48, h=256, w=256)
        buf.fill(image_a, image_b)            # buf[k] = a + (b-a) * (k/steps)
        for k in range(steps):
            display(buf.frame(k))
        buf.step_to(image_c)                  # buf = linspace(b, c)

    ``fill`` and ``step_to`` overwrite the buffer in place — no allocation
    after construction. The compute is fully vectorized (~5 ms at default
    settings), so calling ``step_to`` between trials does not drop frames.
    """

    def __init__(self, steps: int, h: int, w: int, dtype: np.dtype = np.float32):
        if steps < 2:
            raise ValueError("steps must be >= 2")
        self.steps = steps
        self.h = h
        self.w = w
        self.dtype = np.dtype(dtype)
        self._buf = np.empty((steps, h, w), dtype=self.dtype)
        # Per-step weights k/steps for k in [0, steps). Cached.
        self._weights = (np.arange(steps, dtype=self.dtype) / steps)[:, None, None]
        self._endpoint: np.ndarray | None = None
        self._primed = False

    @property
    def current(self) -> np.ndarray:
        """The active ``(steps, H, W)`` buffer (alias used by tests)."""
        return self._buf

    def fill(self, image_a: np.ndarray, image_b: np.ndarray) -> None:
        """Overwrite the buffer with ``linspace(a, b, steps, endpoint=False)``."""
        self._validate_image(image_a)
        self._validate_image(image_b)
        a = np.asarray(image_a, dtype=self.dtype)
        b = np.asarray(image_b, dtype=self.dtype)
        # buf[k] = a + (b - a) * (k / steps), vectorized in two ops.
        delta = (b - a)
        np.multiply(self._weights, delta, out=self._buf)
        self._buf += a  # broadcast (1, H, W) over (steps, H, W) — in-place add
        self._endpoint = b
        self._primed = True

    def step_to(self, image_next: np.ndarray) -> None:
        """Convenience: ``fill(previous_endpoint, image_next)``.

        Used at trial boundaries to advance to the next image.
        """
        if not self._primed or self._endpoint is None:
            raise RuntimeError("fill() must be called before step_to()")
        self.fill(self._endpoint, image_next)

    def frame(self, idx: int) -> np.ndarray:
        if not 0 <= idx < self.steps:
            raise IndexError(f"frame idx {idx} out of [0, {self.steps})")
        return self._buf[idx]

    def _validate_image(self, img: np.ndarray) -> None:
        if img.shape != (self.h, self.w):
            raise ValueError(f"image shape {img.shape} != ({self.h}, {self.w})")
