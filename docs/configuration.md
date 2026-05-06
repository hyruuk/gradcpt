# Configuration

`gradcpt run` builds its configuration from four layers, in increasing precedence:

1. Built-in defaults (the dataclasses in `src/gradcpt/config.py`).
2. A YAML file, if `--config` is given. The bundled
   `src/gradcpt/data/default_config.yaml` is a copy of the dataclass defaults.
3. CLI overrides (`--subject`, `--triggers`, etc.).
4. GUI dialog values, if `--no-gui` is not set.

The merged dict is then cast to a frozen `Config` dataclass and validated;
any violation raises `ConfigError` with the offending field's name.

## Schema

| Path | Type | Default | Meaning |
|---|---|---|---|
| `task.n_trials` | int ≥ 2 | 80 | Trials per block. |
| `task.n_blocks` | int ≥ 1 | 2 | Number of blocks per execution. |
| `task.transition_time_s` | float > 0 | 0.8 | Seconds for a stimulus to fade into the next. |
| `task.prop_dom` | float ∈ (0, 1) | 0.9 | Proportion of dominant (city) trials. |
| `task.expected_refresh_rate_hz` | float \| null | null | Optional sanity-check target. null → trust the measured rate; set e.g. 60 / 120 to validate the active monitor. |
| `task.refresh_rate_tolerance_hz` | float | 2.0 | Warn if `|measured - expected| > this`. (Ignored when `expected_refresh_rate_hz` is null.) |
| `task.refresh_rate_abort_tolerance_hz` | float | 5.0 | Abort if `|measured - expected| > this`. (Ignored when `expected_refresh_rate_hz` is null.) |
| `task.dom_key` | "auto" \| "j" \| "f" | "auto" | "auto" picks one randomly per session. |
| `task.log_extra_keys` | bool | true | Log non-dom-key presses in `_beh.tsv`. |
| `task.seed` | int \| null | null | Determinism. Recorded in `_beh.json`. |
| `task.unambig_low` | float ∈ [0, unambig_high) | 0.4 | Coherence below this → press belongs to previous trial. |
| `task.unambig_high` | float ∈ (unambig_low, 1] | 0.55 | Coherence above this → current trial. |
| `task.benefit_of_doubt_for_nogo` | bool | true | Ambiguous press on no-go → re-route to previous (likely-go) trial. |
| `probe.enabled` | bool | true | Toggle experience-sampling probes off entirely. |
| `probe.next_es_min` | int ≥ 1 | 30 | Min trials before the next probe. |
| `probe.next_es_max` | int ≥ next_es_min | 45 | Max trials before the next probe. |
| `probe.isi_s` | float ≥ 0 | 0.5 | Inter-stimulus interval between probe items. |
| `probe.submit_key` | str | "return" | Key that submits each item. |
| `probe.items_file` | path \| null | null | Override probe items YAML; null → bundled default. |
| `probe.initial_mouse_jitter` | float | 0.05 | Mouse x-jitter (norm units) at item onset. |
| `probe.initial_mouse_y` | float | -0.4 | Mouse y at item onset (norm units). |
| `triggers.backend` | "none" \| "serial" \| "parallel" \| "lsl" | "none" | Hardware trigger backend. |
| `triggers.serial_port` | str \| null | null | Required for `serial`. |
| `triggers.serial_baud` | int | 115200 | Serial baud rate. |
| `triggers.parallel_address` | int \| null | null | Required for `parallel`. |
| `triggers.lsl_stream_name` | str | "gradcpt-events" | LSL stream name. |
| `triggers.lsl_stream_type` | str | "Markers" | LSL stream type. |
| `triggers.pulse_duration_s` | float ≥ 0 | 0.005 | Pulse-then-clear width for serial/parallel. |
| `stimuli.folder` | path \| null | null | null → bundled `stimuli_assets/`. |
| `stimuli.scrambled_enabled` | bool | false | Include the scrambled category. |
| `stimuli.scrambled_role` | "distractor" \| "extra_nogo" \| "extra_go" | "distractor" | Role of scrambled trials when enabled. |
| `stimuli.image_size_px` | int ≥ 8 | 256 | Expected image edge length. |
| `stimuli.apply_circular_mask` | bool | true | Mask off corners outside an inscribed circle. |
| `stimuli.flip_vertical` | bool | true | Preserves the original gradcptpy quirk. Set to false in fresh studies. |
| `stimuli.normalize_to_minus1_plus1` | bool | true | Scale uint8 → float32 in [-1, +1]. |
| `stimuli.display_size` | float ∈ (0, 2] | 0.5 | Drawn size in PsychoPy *height* units (1.0 = full screen height in both axes). The default 0.5 paints a square half the screen height tall — the circular mask makes it appear as a perfect circle regardless of screen aspect ratio. |
| `window.fullscreen` | bool | true | Fullscreen mode. |
| `window.size` | [int, int] | [1920, 1080] | Window pixel size (used as fullscreen target). |
| `window.monitor_name` | str | "testMonitor" | PsychoPy monitor name. |
| `window.color` | [float, float, float] | [0, 0, 0] | Background color in `units` space. |
| `window.units` | str | "norm" | PsychoPy units. |
| `window.screen` | int ≥ 0 | 0 | Screen index. |
| `window.record_frame_intervals` | bool | true | Enable per-frame interval recording. |
| `bids.root` | path | "bids" | Output directory. |
| `bids.subject` | str (alphanumeric) | "" | **Required at runtime.** |
| `bids.session` | str (alphanumeric) \| null | null | Optional session label. |
| `bids.task_label` | str | "gradcpt" | The `task-XXX` segment of filenames. |
| `bids.run_index` | int ≥ 1 \| null | null | null → auto-increment per block. |
| `bids.write_validator_report` | bool | false | Optional bids-validator hook. |

## CLI overrides

The CLI surface intentionally only exposes the most commonly-changed fields:

```
--subject     bids.subject
--session     bids.session
--no-probes   probe.enabled = false
--triggers    triggers.backend
--bids-root   bids.root
--seed        task.seed
--probes-file probe.items_file
```

Everything else (trigger ports, refresh-rate tolerances, image preprocessing
toggles, etc.) lives in YAML.

## GUI fields

When the dialog is shown, these are the editable fields:

* `subject` (required, alphanumeric)
* `session` (optional, alphanumeric or blank)
* `dom_key` (auto / j / f)
* `triggers_backend`
* `probes_enabled`
* `n_trials`, `n_blocks`
* `bids_root`

For deeper changes (refresh-rate tolerance, slider mouse-jitter, etc.) edit
the YAML directly.
