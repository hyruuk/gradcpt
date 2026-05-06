from __future__ import annotations

import logging

import pytest

from gradcpt.timing import (
    RefreshRateMeasurement,
    TimingError,
    check_refresh_rate,
    compute_transition_steps,
    summarize_frames,
)


def test_compute_transition_steps_default_60hz_800ms():
    assert compute_transition_steps(60.0, 0.8) == 48


def test_compute_transition_steps_rounding():
    # 60 * 0.799 = 47.94 → round = 48
    assert compute_transition_steps(60.0, 0.799) == 48
    # 144 * 0.05 = 7.2 → round = 7
    assert compute_transition_steps(144.0, 0.05) == 7


def test_compute_transition_steps_minimum_two():
    # very short transition still floors to 2 frames
    assert compute_transition_steps(60.0, 0.001) == 2


def test_compute_transition_steps_invalid():
    with pytest.raises(ValueError):
        compute_transition_steps(0, 0.8)
    with pytest.raises(ValueError):
        compute_transition_steps(60.0, 0)


def _meas(measured_hz: float, expected_hz: float | None = 60.0) -> RefreshRateMeasurement:
    return RefreshRateMeasurement(
        measured_hz=measured_hz,
        expected_hz=expected_hz,
        deviation_hz=None if expected_hz is None else abs(measured_hz - expected_hz),
        n_warmup_frames=10,
        n_frames_used=100,
    )


def test_check_refresh_rate_skipped_when_expected_is_none(caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="gradcpt.timing"):
        check_refresh_rate(_meas(119.83, expected_hz=None), tolerance_hz=2.0, abort_tolerance_hz=5.0)
    # Should not raise and should not warn — only an info log.
    assert "Measured refresh rate" in caplog.text
    assert "Aborting" not in caplog.text


def test_check_refresh_rate_within_tolerance_silent(caplog):
    with caplog.at_level(logging.WARNING):
        check_refresh_rate(_meas(60.5), tolerance_hz=2.0, abort_tolerance_hz=5.0)
    assert "Refresh-rate deviation" not in caplog.text


def test_check_refresh_rate_warns_between_thresholds(caplog):
    with caplog.at_level(logging.WARNING, logger="gradcpt.timing"):
        check_refresh_rate(_meas(57.0), tolerance_hz=2.0, abort_tolerance_hz=5.0)
    assert "Refresh-rate deviation" in caplog.text


def test_check_refresh_rate_aborts_above_abort_tolerance():
    with pytest.raises(TimingError, match="Aborting"):
        check_refresh_rate(_meas(120.0), tolerance_hz=2.0, abort_tolerance_hz=5.0)


def test_check_refresh_rate_aborts_below():
    with pytest.raises(TimingError):
        check_refresh_rate(_meas(40.0), tolerance_hz=2.0, abort_tolerance_hz=5.0)


def test_summarize_frames_empty():
    s = summarize_frames([], threshold_s=0.025)
    assert s == {"n_frames": 0, "n_dropped": 0, "mean_interval_ms": 0.0, "max_interval_ms": 0.0}


def test_summarize_frames_counts_drops():
    intervals = [0.0167] * 10 + [0.05]  # one ~3-frame drop
    s = summarize_frames(intervals, threshold_s=0.025)
    assert s["n_frames"] == 11
    assert s["n_dropped"] == 1
    assert s["max_interval_ms"] == pytest.approx(50.0, rel=1e-3)
    assert s["mean_interval_ms"] > 16.0
