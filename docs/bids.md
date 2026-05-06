# BIDS output

`gradcpt run` writes data in the BIDS-Behavioral layout (BEP016).
Modality folder is `beh/`. **One block of trials = one BIDS run**, so a
2-block session writes two `..._run-NN_events.tsv` files.

## Layout

```
{bids.root}/
├── dataset_description.json
├── participants.tsv
├── participants.json
├── README
├── task-gradcpt_events.json
├── task-gradcpt_beh.json
└── sub-<label>/
    └── [ses-<label>/]
        └── beh/
            ├── sub-<label>[_ses-<label>]_task-gradcpt_run-NN_events.tsv
            ├── sub-<label>[_ses-<label>]_task-gradcpt_run-NN_beh.tsv
            └── sub-<label>[_ses-<label>]_task-gradcpt_run-NN_beh.json
```

## `events.tsv`

The analysis-ready table. Time-sorted; one row per event:

| Column | Type | Description |
|---|---|---|
| `onset` | float (s) | Onset relative to the run's start. |
| `duration` | float (s) | Duration of the event. |
| `trial_type` | str | Event class (see codebook below). |
| `stim_category` | str | `dom`, `nondom`, or `scrambled`. |
| `stim_id` | str | Image filename stem. |
| `response` | str | Key pressed (or `n/a`). |
| `response_time` | float (s) | RT post reconciliation. |
| `coherence_at_press` | float | Coherence at the moment of keypress (if applicable). |
| `accuracy` | int | 1 if correct, 0 if error. |
| `ambiguous` | bool | True if the press required ambiguous-band reconciliation. |
| `probe_id` | int | Sequential probe number within the run. |
| `item_name` | str | Probe item name. |
| `item_response` | float ∈ [0, 1] | Slider value. |
| `n_dropped_in_trial` | int | Frames in this trial that exceeded the refresh threshold. |
| `block_idx` | int | 0-indexed block number within the execution. |
| `trial_idx` | int | 1-indexed trial within the block. |

`trial_type` values:
- `gradcpt_dom_trial`, `gradcpt_nondom_trial`, `gradcpt_scrambled_trial`
- `block_start`, `block_end`
- `probe_start`, `probe_item`, `probe_submit`, `probe_end`

## `_beh.tsv`

The raw keypress log. **Every press is recorded — none are deduplicated.**
Use this for forensic analysis or for re-running reconciliation with
different thresholds.

| Column | Description |
|---|---|
| `timestamp_global_s` | PsychoPy core-clock time. |
| `timestamp_trial_relative_s` | Time relative to current trial onset. |
| `block_idx`, `trial_idx`, `trial_condition`, `image_id` | Trial provenance. |
| `coherence_at_press` | Coherence at press. |
| `frame_idx_in_trial` | Frame index (0-based). |
| `key` | Key pressed. |
| `provisional_assigned_trial`, `provisional_assignment_kind` | Online provisional assignment (`previous` / `current` / `ambiguous`). |
| `rt_to_press_s` | RT to press from current trial onset. |

## `_beh.json`

Per-run metadata:

```json
{
  "TaskName": "GradCPT",
  "GradcptVersion": "0.1.0",
  "CodebookVersion": "1",
  "RunIndex": 1,
  "BlockIndex": 0,
  "DomKey": "j",
  "Seed": 42,
  "RefreshRateMeasured": {"measured_hz": 60.0, "expected_hz": 60.0, "deviation_hz": 0.0},
  "FrameIntervalSummary": {"n_frames": 4800, "n_dropped": 1, "mean_interval_ms": 16.66, "max_interval_ms": 17.10},
  "ConfigSnapshot": { ... full Config ... }
}
```

`ConfigSnapshot` is a complete dump of the resolved `Config` for full
reproducibility — re-running with the same `Seed` and the same snapshot
gives the same trial sequence.

## Run auto-increment

By default, `bids.run_index` is null and `BIDSWriter` scans
`sub-<label>/[ses-<label>/]beh/` for the highest existing
`..._run-NN_events.tsv` and uses `max+1`. If you set `--run-index N`
explicitly, that's the run number for the *first* block; subsequent blocks
in the same execution get `N+1`, `N+2`, etc.

If the target file already exists, `BIDSWriter` writes anyway and emits a
warning — re-running a session is occasionally necessary, and we don't want
to abort halfway through.

## Sanity check

`BIDSWriter.sanity_check()` verifies:

- All run files exist.
- `events.tsv` has no NaN onsets.
- Events are time-sorted by onset.

This runs automatically at the end of `run_experiment`. For full
BIDS-validator compliance, install Node.js + `bids-validator` and run:

```bash
npx bids-validator path/to/bids/
```
