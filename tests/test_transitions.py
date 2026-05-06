from __future__ import annotations

import numpy as np
import pytest

from gradcpt.transitions import TransitionBuffer


def test_construct_allocates_buffer_of_correct_shape():
    buf = TransitionBuffer(steps=48, h=256, w=256)
    assert buf.current.shape == (48, 256, 256)
    assert buf.current.dtype == np.float32


def test_steps_must_be_at_least_two():
    with pytest.raises(ValueError):
        TransitionBuffer(steps=1, h=4, w=4)


def test_fill_writes_linspace_into_buffer():
    a = np.zeros((4, 4), dtype=np.float32)
    b = np.ones((4, 4), dtype=np.float32)
    buf = TransitionBuffer(steps=10, h=4, w=4)
    buf.fill(a, b)
    expected = np.linspace(a, b, 10, endpoint=False, dtype=np.float32)
    # Our vectorized fill (a + delta*k/steps) differs from np.linspace by
    # one float32 ulp; tolerable for stimulus rendering.
    np.testing.assert_allclose(buf.current, expected, rtol=1e-6, atol=1e-6)


def test_step_to_uses_previous_endpoint():
    a = np.zeros((4, 4), dtype=np.float32)
    b = np.full((4, 4), 0.5, dtype=np.float32)
    c = np.ones((4, 4), dtype=np.float32)
    buf = TransitionBuffer(steps=8, h=4, w=4)
    buf.fill(a, b)
    buf.step_to(c)
    expected = np.linspace(b, c, 8, endpoint=False, dtype=np.float32)
    np.testing.assert_allclose(buf.current, expected, rtol=1e-6, atol=1e-6)


def test_step_to_before_fill_raises():
    buf = TransitionBuffer(steps=4, h=4, w=4)
    with pytest.raises(RuntimeError, match="fill"):
        buf.step_to(np.zeros((4, 4), dtype=np.float32))


def test_frame_returns_view_into_current():
    a = np.zeros((4, 4), dtype=np.float32)
    b = np.ones((4, 4), dtype=np.float32)
    buf = TransitionBuffer(steps=4, h=4, w=4)
    buf.fill(a, b)
    frame0 = buf.frame(0)
    assert np.shares_memory(frame0, buf.current)


def test_frame_index_out_of_range_raises():
    buf = TransitionBuffer(steps=4, h=4, w=4)
    buf.fill(np.zeros((4, 4), dtype=np.float32), np.ones((4, 4), dtype=np.float32))
    with pytest.raises(IndexError):
        buf.frame(4)
    with pytest.raises(IndexError):
        buf.frame(-1)


def test_image_shape_mismatch_raises():
    buf = TransitionBuffer(steps=4, h=4, w=4)
    with pytest.raises(ValueError):
        buf.fill(np.zeros((5, 5), dtype=np.float32), np.zeros((4, 4), dtype=np.float32))


def test_fill_does_not_allocate_new_buffer():
    """The same memory is reused across fill() calls."""
    buf = TransitionBuffer(steps=4, h=4, w=4)
    a = np.zeros((4, 4), dtype=np.float32)
    b = np.ones((4, 4), dtype=np.float32)
    buf.fill(a, b)
    addr_before = buf.current.ctypes.data
    buf.fill(b, a)
    addr_after = buf.current.ctypes.data
    assert addr_before == addr_after


def test_fill_endpoint_recorded_for_step_to():
    """After fill(a, b), step_to(c) should produce linspace(b, c)."""
    a = np.zeros((4, 4), dtype=np.float32)
    b = np.full((4, 4), 0.3, dtype=np.float32)
    c = np.full((4, 4), 0.9, dtype=np.float32)
    buf = TransitionBuffer(steps=6, h=4, w=4)
    buf.fill(a, b)
    buf.step_to(c)
    np.testing.assert_allclose(buf.current[0], b, rtol=1e-6, atol=1e-6)


def test_fill_does_not_corrupt_previous_frames_during_trial():
    """Frames 0..steps-1 should all hold the linspace immediately after fill().

    This test catches the regression where an earlier double-buffered design
    swapped buffers mid-trial and showed garbage on later frames.
    """
    a = np.full((4, 4), -1.0, dtype=np.float32)
    b = np.full((4, 4), 1.0, dtype=np.float32)
    buf = TransitionBuffer(steps=10, h=4, w=4)
    buf.fill(a, b)
    expected_steps = np.linspace(a, b, 10, endpoint=False, dtype=np.float32)
    for k in range(10):
        np.testing.assert_allclose(buf.frame(k), expected_steps[k], rtol=1e-6, atol=1e-6)
