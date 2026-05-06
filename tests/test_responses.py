from __future__ import annotations

import pandas as pd
import pytest

from gradcpt.responses import KeyPressLog, KeyPressRecord, provisional_assign


def make_record(**overrides) -> KeyPressRecord:
    base = dict(
        timestamp_global_s=10.0,
        timestamp_trial_relative_s=0.5,
        block_idx=0,
        trial_idx=3,
        trial_condition="dom",
        image_id="d1",
        coherence_at_press=0.7,
        frame_idx_in_trial=33,
        key="j",
        provisional_assigned_trial=3,
        provisional_assignment_kind="current",
        rt_to_press_s=0.5,
    )
    base.update(overrides)
    return KeyPressRecord(**base)


def test_provisional_assign_low_coherence_to_previous():
    assigned, kind = provisional_assign(0.3, current_trial=5)
    assert (assigned, kind) == (4, "previous")


def test_provisional_assign_high_coherence_to_current():
    assigned, kind = provisional_assign(0.7, current_trial=5)
    assert (assigned, kind) == (5, "current")


def test_provisional_assign_ambiguous_in_band():
    assigned, kind = provisional_assign(0.5, current_trial=5)
    assert (assigned, kind) == (5, "ambiguous")


def test_provisional_assign_threshold_boundaries():
    # exactly at low threshold → still ambiguous (low is strict <)
    assert provisional_assign(0.4, 5) == (5, "ambiguous")
    # exactly at high threshold → still ambiguous (high is strict >)
    assert provisional_assign(0.55, 5) == (5, "ambiguous")
    assert provisional_assign(0.39999, 5) == (4, "previous")
    assert provisional_assign(0.55001, 5) == (5, "current")


def test_provisional_assign_custom_thresholds():
    assert provisional_assign(0.5, 5, unambig_low=0.3, unambig_high=0.7) == (5, "ambiguous")
    assert provisional_assign(0.5, 5, unambig_low=0.6, unambig_high=0.7) == (4, "previous")


def test_keypress_log_append_and_iterate():
    log = KeyPressLog()
    log.append(make_record(trial_idx=1))
    log.append(make_record(trial_idx=2))
    assert len(log) == 2
    assert [r.trial_idx for r in log] == [1, 2]


def test_keypress_log_to_dataframe_columns_match_schema():
    log = KeyPressLog()
    log.append(make_record())
    df = log.to_dataframe()
    assert list(df.columns) == list(KeyPressLog.COLUMNS)
    assert len(df) == 1


def test_keypress_log_empty_dataframe_has_correct_columns():
    df = KeyPressLog().to_dataframe()
    assert list(df.columns) == list(KeyPressLog.COLUMNS)
    assert len(df) == 0


def test_keypress_log_to_tsv_uses_n_a_for_missing(tmp_path):
    log = KeyPressLog()
    log.append(make_record(rt_to_press_s=float("nan")))
    out = tmp_path / "log.tsv"
    log.to_tsv(out)
    text = out.read_text()
    assert "\t" in text  # tab-separated
    assert "n/a" in text  # NaN written as BIDS-canonical "n/a"


def test_keypress_log_extend_adds_records():
    log = KeyPressLog()
    log.extend([make_record(trial_idx=i) for i in range(3)])
    assert len(log) == 3
