# Frame-accurate timing

GradCPT's stimulus presentation depends on each transition lasting exactly
`transition_time_s` (default 0.8 s). The original gradcptpy implementation
measured the refresh rate by counting how many frames fell into each integer
second over a 5-second window, then averaged the bucket counts. That has
±0.5 Hz quantization noise built in and includes startup transients.

This package replaces that with three layers of correctness:

## 1. Refresh-rate measurement

`gradcpt.timing.measure_refresh_rate` calls
`Window.getActualFrameRate(nIdentical=10, nMaxFrames=100, nWarmUpFrames=10,
threshold=1)`. PsychoPy waits for ten consecutive vsync flips that fall
within 1 ms of each other before returning. If that fails (rare, but possible
with a misconfigured monitor), we fall back to the median of 30 flip
intervals.

The measured rate is logged. If `task.expected_refresh_rate_hz` is set
(default: null), the measured rate is also compared to it:

* Within `refresh_rate_tolerance_hz` (default 2 Hz) → silent.
* Above tolerance, below `refresh_rate_abort_tolerance_hz` (default 5 Hz) → log a warning.
* Above abort tolerance → raise `TimingError` and halt the experiment.

When `expected_refresh_rate_hz` is null (the default), the cross-check is
skipped — we trust whatever the monitor reports. Set it to your declared
target (e.g. `60` or `120`) to catch the "ran on the wrong screen" failure
mode.

## 2. Frame-counted trial loop

Each trial is a `for frame_idx in range(transition_steps)` loop. We do **not**
schedule per-trial durations against a wall-clock; we let v-sync drive the
timing. `Window` is opened with `waitBlanking=True` and `useFBO=True`, and
each `win.flip()` blocks until the next vertical retrace.

`transition_steps = max(2, round(measured_hz × transition_time_s))`.

At default 60 Hz × 0.8 s, that's 48 frames per trial. Trial duration is then
exactly `48 / measured_hz` plus per-frame OS jitter, with no accumulating
drift across trials. RTs are computed against the v-sync timestamp of the
trial's first flip — never against `datetime.now()`.

## 3. Dropped-frame logging

`Window.recordFrameIntervals = True` collects every flip's interval.
`Window.refreshThreshold = 1.5 / measured_hz` flags any interval longer than
1.5 frames as a "drop".

`gradcpt.timing.summarize_frames` produces:

```python
{
  "n_frames": 4800,
  "n_dropped": 3,
  "mean_interval_ms": 16.66,
  "max_interval_ms": 24.10,
}
```

This summary is written to `..._beh.json` per block. Per-trial drop counts
also land in `events.tsv` as `n_dropped_in_trial` — useful for excluding
trials post-hoc.

## 4. Pre-computed transitions

`gradcpt.transitions.TransitionBuffer` holds two pre-allocated `(steps, H, W)`
float32 buffers. At trial `t` we display from `current`; during frames 1+ we
write the next transition into `next`. At trial end the roles swap. Memory
cost: `2 × 48 × 256² × 4 B ≈ 24 MB` at default settings — negligible — but
crucially **no allocation happens during the timing-critical part of the
loop**.

## What can still go wrong

* **Compositing window managers** (X11 with effects, Wayland) sometimes add
  one frame of latency. PsychoPy's `getActualFrameRate` is robust to this,
  but timestamps will be one frame off in absolute terms. Use LSL or hardware
  triggers for sub-frame alignment with EEG.
* **Power-management governors** can throttle the GPU. Set the system to
  "performance" mode during data collection.
* **Background processes** (browsers, sync daemons) can cause sporadic frame
  drops. Use a dedicated stimulus machine or close everything before recording.

The `n_dropped` columns let you detect and exclude affected trials.
