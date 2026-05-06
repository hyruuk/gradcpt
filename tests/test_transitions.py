from __future__ import annotations

import numpy as np
import pytest

from gradcpt.transitions import TransitionBuffer


def test_construct_allocates_two_buffers_of_correct_shape():
    buf = TransitionBuffer(steps=48, h=256, w=256)
    assert buf.current.shape == (48, 256, 256)
    assert buf.next.shape == (48, 256, 256)
    assert buf.current.dtype == np.float32
    # The two underlying buffers must be distinct memory.
    assert not np.shares_memory(buf.current, buf.next)


def test_steps_must_be_at_least_two():
    with pytest.raises(ValueError):
        TransitionBuffer(steps=1, h=4, w=4)


def test_prime_fills_current_with_linspace():
    a = np.zeros((4, 4), dtype=np.float32)
    b = np.ones((4, 4), dtype=np.float32)
    buf = TransitionBuffer(steps=10, h=4, w=4)
    buf.prime(a, b)
    expected = np.linspace(a, b, 10, endpoint=False, dtype=np.float32)
    np.testing.assert_allclose(buf.current, expected)


def test_advance_swaps_and_writes_into_next_buffer():
    a = np.zeros((4, 4), dtype=np.float32)
    b = np.ones((4, 4), dtype=np.float32) * 0.5
    c = np.ones((4, 4), dtype=np.float32)
    buf = TransitionBuffer(steps=8, h=4, w=4)
    buf.prime(a, b)
    first_current_id = id(buf.current)
    buf.advance(c)
    # Buffers should have swapped roles
    assert id(buf.current) != first_current_id
    # New next is linspace(b → c)
    expected = np.linspace(b, c, 8, endpoint=False, dtype=np.float32)
    np.testing.assert_allclose(buf.next, expected)


def test_advance_before_prime_raises():
    buf = TransitionBuffer(steps=4, h=4, w=4)
    with pytest.raises(RuntimeError, match="prime"):
        buf.advance(np.zeros((4, 4), dtype=np.float32))


def test_frame_returns_view_into_current():
    a = np.zeros((4, 4), dtype=np.float32)
    b = np.ones((4, 4), dtype=np.float32)
    buf = TransitionBuffer(steps=4, h=4, w=4)
    buf.prime(a, b)
    frame0 = buf.frame(0)
    assert np.shares_memory(frame0, buf.current)


def test_frame_index_out_of_range_raises():
    buf = TransitionBuffer(steps=4, h=4, w=4)
    buf.prime(np.zeros((4, 4), dtype=np.float32), np.ones((4, 4), dtype=np.float32))
    with pytest.raises(IndexError):
        buf.frame(4)
    with pytest.raises(IndexError):
        buf.frame(-1)


def test_image_shape_mismatch_raises():
    buf = TransitionBuffer(steps=4, h=4, w=4)
    with pytest.raises(ValueError):
        buf.prime(np.zeros((5, 5), dtype=np.float32), np.zeros((4, 4), dtype=np.float32))
