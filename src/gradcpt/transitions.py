"""Double-buffered transition generator.

The trial loop walks ``transition_steps`` frames per trial, each frame a
linear interpolation between the previous and current images. Generating a
fresh interpolation array (~12 MB at default settings) inside the
timing-critical part of the trial loop is what causes the original
implementation's "extra frame somewhere" jitter; we avoid that by
maintaining two pre-allocated buffers and computing the *next* trial's
transition during the *current* trial's playback frames.

Memory at default (256×256, 48 steps, float32): 2 × 12 MB ≈ 24 MB. Cheap.
"""
from __future__ import annotations

import numpy as np


class TransitionBuffer:
    """Two pre-allocated float32 buffers of shape (steps, H, W).

    Usage::

        buf = TransitionBuffer(steps=48, h=256, w=256)
        buf.prime(image_a, image_b)            # buf.current = linspace(a, b)
        for f in range(steps):
            display(buf.frame(f))
        buf.advance(image_c)                   # current ← next; next ← linspace(b, c)

    The ``advance`` call *swaps* the role of the two buffers and writes the
    new linspace into what becomes ``next``. No allocations after construction.
    """

    def __init__(self, steps: int, h: int, w: int, dtype: np.dtype = np.float32):
        if steps < 2:
            raise ValueError("steps must be >= 2")
        self.steps = steps
        self.h = h
        self.w = w
        self.dtype = np.dtype(dtype)
        self._buf_a = np.empty((steps, h, w), dtype=self.dtype)
        self._buf_b = np.empty((steps, h, w), dtype=self.dtype)
        self._current = self._buf_a
        self._next = self._buf_b
        self._endpoint_current: np.ndarray | None = None  # last frame of current
        self._primed = False

    @property
    def current(self) -> np.ndarray:
        return self._current

    @property
    def next(self) -> np.ndarray:
        return self._next

    def prime(self, image_a: np.ndarray, image_b: np.ndarray) -> None:
        """Initialize ``current`` with linspace(a → b). Must be called first."""
        self._validate_image(image_a)
        self._validate_image(image_b)
        self._fill_linspace_into(self._current, image_a, image_b)
        self._endpoint_current = np.asarray(image_b, dtype=self.dtype)
        self._primed = True

    def advance(self, image_next: np.ndarray) -> None:
        """Swap buffers; write linspace(prev_end → image_next) into the new ``next``.

        After this call, ``current`` is the just-played transition's *successor*
        (i.e. the buffer previously known as ``next``), and ``next`` holds the
        transition from the new endpoint to ``image_next``.
        """
        if not self._primed:
            raise RuntimeError("prime() must be called before advance()")
        self._validate_image(image_next)
        # Swap roles
        self._current, self._next = self._next, self._current
        # Compute new transition into the now-spare buffer
        self._fill_linspace_into(self._next, self._endpoint_current, image_next)
        self._endpoint_current = np.asarray(image_next, dtype=self.dtype)

    def _fill_linspace_into(
        self, buf: np.ndarray, a: np.ndarray, b: np.ndarray
    ) -> None:
        """Compute linspace(a, b, steps, endpoint=False) directly into ``buf``.

        Avoids re-allocating the full (steps, H, W) array each call. The
        intermediate ``delta`` is a (H, W) block — small.
        """
        a = np.asarray(a, dtype=self.dtype)
        b = np.asarray(b, dtype=self.dtype)
        delta = (b - a)
        steps = self.steps
        # frame_k = a + delta * (k / steps)
        for k in range(steps):
            np.multiply(delta, k / steps, out=buf[k])
            np.add(buf[k], a, out=buf[k])

    def frame(self, idx: int) -> np.ndarray:
        if not 0 <= idx < self.steps:
            raise IndexError(f"frame idx {idx} out of [0, {self.steps})")
        return self._current[idx]

    def _validate_image(self, img: np.ndarray) -> None:
        if img.shape != (self.h, self.w):
            raise ValueError(f"image shape {img.shape} != ({self.h}, {self.w})")
