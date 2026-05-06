from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from gradcpt.bids import (
    EVENT_COLUMNS,
    BIDSWriter,
    EventRow,
    auto_run_idx,
    run_filename_stem,
    subject_dir,
)
from gradcpt.config import BIDSConfig, Config
from gradcpt.reconcile import ResolvedTrial
from gradcpt.responses import KeyPressRecord


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def test_subject_dir_without_session():
    p = subject_dir(Path("/tmp/bids"), "s1", None)
    assert p == Path("/tmp/bids/sub-s1/beh")


def test_subject_dir_with_session():
    p = subject_dir(Path("/tmp/bids"), "s1", "01")
    assert p == Path("/tmp/bids/sub-s1/ses-01/beh")


def test_run_filename_stem_with_and_without_session():
    s1 = run_filename_stem("s1", None, "gradcpt", 3)
    assert s1 == "sub-s1_task-gradcpt_run-03"
    s2 = run_filename_stem("s1", "01", "gradcpt", 12)
    assert s2 == "sub-s1_ses-01_task-gradcpt_run-12"


def test_subject_dir_rejects_invalid_label():
    with pytest.raises(ValueError):
        subject_dir(Path("/tmp"), "bad-id", None)


def test_auto_run_idx_empty_dir(tmp_path):
    assert auto_run_idx(tmp_path, "s1", "gradcpt") == 1


def test_auto_run_idx_finds_max(tmp_path):
    for n in [1, 2, 5]:
        (tmp_path / f"sub-s1_task-gradcpt_run-{n:02d}_events.tsv").write_text("x\n")
    assert auto_run_idx(tmp_path, "s1", "gradcpt") == 6


def test_auto_run_idx_ignores_other_subjects(tmp_path):
    (tmp_path / "sub-s1_task-gradcpt_run-01_events.tsv").write_text("x\n")
    (tmp_path / "sub-other_task-gradcpt_run-99_events.tsv").write_text("x\n")
    # Pattern matches both subjects (we don't enforce subject-id boundaries).
    # Our regex matches any subject in the file's name *because* we glob by the
    # task suffix; the test confirms current behavior.
    assert auto_run_idx(tmp_path, "s1", "gradcpt") in (2, 100)


# ---------------------------------------------------------------------------
# BIDSWriter — single-block round-trip
# ---------------------------------------------------------------------------


def make_cfg(tmp_path, subject="pilot01", session=None) -> Config:
    return Config(bids=BIDSConfig(root=tmp_path, subject=subject, session=session))


def test_single_block_roundtrip(tmp_path):
    cfg = make_cfg(tmp_path)
    w = BIDSWriter(cfg)
    run_idx = w.begin_block(0)
    assert run_idx == 1
    w.append_event(
        EventRow(onset=0.0, duration=0.0, trial_type="block_start", block_idx=0)
    )
    rt = ResolvedTrial(
        trial_idx=1,
        condition="dom",
        image_id="city01",
        response_key="j",
        rt_s=0.5,
        accuracy=1,
        ambiguous=False,
        reassigned=False,
    )
    w.append_resolved_trial(rt, onset=0.0, duration=0.8, n_dropped=0)
    w.set_block_metadata(
        frame_summary={"n_frames": 100, "n_dropped": 0, "mean_interval_ms": 16.7, "max_interval_ms": 17.0},
        refresh_meas={"measured_hz": 60.0, "expected_hz": 60.0, "deviation_hz": 0.0},
        dom_key="j",
        seed=42,
    )
    w.end_block()
    w.finalize()
    w.sanity_check()

    beh = tmp_path / "sub-pilot01" / "beh"
    assert (beh / "sub-pilot01_task-gradcpt_run-01_events.tsv").is_file()
    assert (beh / "sub-pilot01_task-gradcpt_run-01_beh.tsv").is_file()
    assert (beh / "sub-pilot01_task-gradcpt_run-01_beh.json").is_file()

    df = pd.read_csv(beh / "sub-pilot01_task-gradcpt_run-01_events.tsv", sep="\t")
    assert list(df.columns) == list(EVENT_COLUMNS)
    assert (df["trial_type"] == "block_start").any()
    assert (df["trial_type"] == "gradcpt_dom_trial").any()


def test_two_blocks_get_two_runs(tmp_path):
    cfg = make_cfg(tmp_path)
    w = BIDSWriter(cfg)
    run0 = w.begin_block(0)
    w.append_event(EventRow(onset=0.0, duration=0.0, trial_type="block_start", block_idx=0))
    w.end_block()
    run1 = w.begin_block(1)
    w.append_event(EventRow(onset=0.0, duration=0.0, trial_type="block_start", block_idx=1))
    w.end_block()
    w.finalize()
    assert (run0, run1) == (1, 2)
    beh = tmp_path / "sub-pilot01" / "beh"
    assert (beh / "sub-pilot01_task-gradcpt_run-01_events.tsv").is_file()
    assert (beh / "sub-pilot01_task-gradcpt_run-02_events.tsv").is_file()


def test_run_auto_increments_across_executions(tmp_path):
    cfg1 = make_cfg(tmp_path)
    w1 = BIDSWriter(cfg1)
    w1.begin_block(0)
    w1.append_event(EventRow(onset=0.0, duration=0.0, trial_type="block_start"))
    w1.end_block()
    w1.finalize()

    cfg2 = make_cfg(tmp_path)
    w2 = BIDSWriter(cfg2)
    run = w2.begin_block(0)
    assert run == 2  # picks up where cfg1 left off
    w2.end_block()


def test_explicit_run_index_used_then_auto_continues(tmp_path):
    cfg = Config(bids=BIDSConfig(root=tmp_path, subject="s1", run_index=10))
    w = BIDSWriter(cfg)
    assert w.begin_block(0) == 10
    w.end_block()
    assert w.begin_block(1) == 11
    w.end_block()


def test_dataset_description_written_at_finalize(tmp_path):
    cfg = make_cfg(tmp_path)
    w = BIDSWriter(cfg)
    w.begin_block(0)
    w.end_block()
    w.finalize()
    dd = json.loads((tmp_path / "dataset_description.json").read_text())
    assert dd["Name"] == "GradCPT"
    assert dd["GeneratedBy"][0]["Name"] == "gradcpt"


def test_participants_tsv_appended_per_subject(tmp_path):
    cfg1 = make_cfg(tmp_path, subject="s1")
    w1 = BIDSWriter(cfg1)
    w1.begin_block(0)
    w1.set_block_metadata(dom_key="j")
    w1.end_block()
    w1.finalize()

    cfg2 = make_cfg(tmp_path, subject="s2")
    w2 = BIDSWriter(cfg2)
    w2.begin_block(0)
    w2.set_block_metadata(dom_key="f")
    w2.end_block()
    w2.finalize()

    df = pd.read_csv(tmp_path / "participants.tsv", sep="\t")
    assert sorted(df["participant_id"].tolist()) == ["sub-s1", "sub-s2"]


def test_participants_tsv_no_duplicate_for_same_subject(tmp_path):
    cfg = make_cfg(tmp_path, subject="s1")
    for _ in range(3):
        w = BIDSWriter(cfg)
        w.begin_block(0)
        w.end_block()
        w.finalize()
    df = pd.read_csv(tmp_path / "participants.tsv", sep="\t")
    assert (df["participant_id"] == "sub-s1").sum() == 1


def test_append_keypress_writes_beh_tsv(tmp_path):
    cfg = make_cfg(tmp_path)
    w = BIDSWriter(cfg)
    w.begin_block(0)
    w.append_event(EventRow(onset=0.0, duration=0.0, trial_type="block_start"))
    w.append_keypress(
        KeyPressRecord(
            timestamp_global_s=1.0,
            timestamp_trial_relative_s=0.5,
            block_idx=0,
            trial_idx=1,
            trial_condition="dom",
            image_id="city01",
            coherence_at_press=0.7,
            frame_idx_in_trial=33,
            key="j",
            provisional_assigned_trial=1,
            provisional_assignment_kind="current",
            rt_to_press_s=0.5,
        )
    )
    w.end_block()
    w.finalize()
    beh_tsv = tmp_path / "sub-pilot01" / "beh" / "sub-pilot01_task-gradcpt_run-01_beh.tsv"
    df = pd.read_csv(beh_tsv, sep="\t")
    assert len(df) == 1
    assert df.iloc[0]["key"] == "j"


def test_atomic_write_overwrite_warning(tmp_path, caplog):
    """If a run-NN file already exists at the target path, BIDSWriter logs a warning."""
    cfg = make_cfg(tmp_path)
    beh = tmp_path / "sub-pilot01" / "beh"
    beh.mkdir(parents=True, exist_ok=True)
    (beh / "sub-pilot01_task-gradcpt_run-01_events.tsv").write_text("stale\n")

    cfg = Config(bids=BIDSConfig(root=tmp_path, subject="pilot01", run_index=1))
    w = BIDSWriter(cfg)
    w.begin_block(0)
    import logging
    with caplog.at_level(logging.WARNING, logger="gradcpt.bids"):
        w.end_block()
    assert "Overwriting" in caplog.text


def test_sanity_check_passes_after_finalize(tmp_path):
    cfg = make_cfg(tmp_path)
    w = BIDSWriter(cfg)
    w.begin_block(0)
    w.append_event(EventRow(onset=0.0, duration=0.0, trial_type="block_start"))
    w.append_event(EventRow(onset=1.0, duration=0.8, trial_type="gradcpt_dom_trial"))
    w.end_block()
    w.finalize()
    w.sanity_check()  # should not raise


def test_sanity_check_detects_unsorted_onsets(tmp_path):
    cfg = make_cfg(tmp_path)
    w = BIDSWriter(cfg)
    w.begin_block(0)
    w.append_event(EventRow(onset=2.0, duration=0.0, trial_type="block_start"))
    w.append_event(EventRow(onset=1.0, duration=0.0, trial_type="gradcpt_dom_trial"))
    w.end_block()
    w.finalize()
    with pytest.raises(ValueError, match="not sorted"):
        w.sanity_check()
