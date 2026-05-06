# Triggers

Hardware-trigger backends are pluggable. Pick one in
`triggers.backend` (or pass `--triggers` on the CLI). The codebook below
enumerates which integer goes with which event.

## Backends

### `none` (default)
A no-op sender. No triggers are emitted. Use when running without external
recording hardware.

### `serial`
Writes a single byte per event to a serial device. Required config:

```yaml
triggers:
  backend: serial
  serial_port: /dev/ttyACM0
  serial_baud: 115200
  pulse_duration_s: 0.005
```

After each `send`, a `\x00` zero byte is scheduled to be written
`pulse_duration_s` later (default 5 ms) so downstream hardware that does
edge-detection sees a clean falling edge between events. Set
`pulse_duration_s: 0` to disable the clear and let the byte persist.

Install the optional dep:

```bash
uv pip install -e ".[serial]"
```

### `parallel`
Uses `psychopy.parallel`. Sets the data byte and schedules a `setData(0)`
clear after `pulse_duration_s`.

```yaml
triggers:
  backend: parallel
  parallel_address: 0x378
  pulse_duration_s: 0.005
```

On Linux this requires `pyparallel` and access to the parallel-port device
(usually root or a `dialout` group membership). On Windows install
`inpoutx64.dll` per PsychoPy documentation.

### `lsl`
Pushes a string sample per event to a Lab Streaming Layer marker outlet.

```yaml
triggers:
  backend: lsl
  lsl_stream_name: gradcpt-events
  lsl_stream_type: Markers
```

Recording software (LabRecorder, etc.) listens on the network and timestamps
events in LSL clock space. For sub-frame alignment with EEG, prefer LSL —
all your recording streams (EEG, eye-tracker, gradcpt markers) end up on the
same clock and are aligned automatically.

Install:

```bash
uv pip install -e ".[lsl]"
```

## Codebook

Stable integer codes (and their names in LSL string form):

| Code | Name | When |
|---|---|---|
| 1 | `EXPERIMENT_START` | First flip of the experiment. |
| 2 | `EXPERIMENT_END` | Right before the debrief screen. |
| 10 | `BLOCK_START` | First flip of a block. |
| 11 | `BLOCK_END` | Last flip of a block. |
| 20 | `TRIAL_ONSET_DOM` | Frame 0 of a city (go) trial. |
| 21 | `TRIAL_ONSET_NONDOM` | Frame 0 of a mountain (no-go) trial. |
| 22 | `TRIAL_ONSET_SCRAMBLED` | Frame 0 of a scrambled trial (when enabled). |
| 30 | `RESPONSE_DOM_KEY` | Dominant-response key was pressed. |
| 31 | `RESPONSE_NONDOM_KEY` | Non-dominant key was pressed (commission error). |
| 40 | `PROBE_START` | First flip of a probe. |
| 41 | `PROBE_END` | Last flip of a probe. |
| 50 | `PROBE_ITEM_ONSET` | A slider item is shown. |
| 51 | `PROBE_ITEM_RESPONSE` | First slider movement on an item. |
| 52 | `PROBE_ITEM_SUBMIT` | Enter pressed for an item. |

The codebook is also written into `dataset_description.json` (under
`GeneratedBy.CodebookVersion`) and into `task-gradcpt_events.json` (as the
`Codebook` and `CodebookDescriptions` fields), so analysts always have the
mapping next to the data.

## Latency notes

Triggers are emitted via `win.callOnFlip(sender.send, code, label=...)`,
which queues the call to fire **immediately after the next vertical retrace**.
That means the trigger byte hits the wire synchronously with the screen
refresh — the dominant latency source is the v-sync wait, which is exactly
the alignment we want.

Per-backend latency floor (after v-sync):

* `parallel`: microseconds — direct port write.
* `serial`: ~50 µs at 115200 baud (one byte = 8 data bits + start/stop).
* `lsl`: ~1 frame (16 ms at 60 Hz) network round-trip in a typical setup, but
  every recording device on the same LSL network shares a clock so the
  *relative* alignment within the LSL stream is sub-millisecond.

For EEG synchronization, the canonical approach is LSL: stream EEG data and
gradcpt markers into LabRecorder, save as XDF, post-hoc align using LSL
timestamps.
