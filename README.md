# gradcpt

A robust PsychoPy implementation of the gradual-onset continuous performance task
(GradCPT; Esterman et al. 2013). Optional thought probes, pluggable triggers
(serial / parallel / LSL / none), online + offline response-to-trial mapping,
and BIDS-formatted output.

This package is a clean-room replacement of
[`gradcptpy`](https://github.com/DynamicBrainMind/gradcptpy). The original is
preserved as a sibling directory and is not modified.

## Quickstart

```bash
# clone and enter the package
cd /path/to/gradcpt

# create a venv with uv (Python 3.10) and install in dev mode
uv venv --python 3.10
uv pip install -e ".[dev]"

# run the test suite (no display required)
uv run pytest
```

To actually run the experiment you also need PsychoPy. PsychoPy 2024.2.x
declares a broken transitive (`pypi-search`, not on PyPI) and on Linux its
`wxPython` dep only ships as source — install both with the bundled script:

```bash
./scripts/install_psychopy.sh
uv run gradcpt run --subject pilot01 --bids-root ./bids
```

The script installs the prebuilt wxPython wheel for your distro from
extras.wxpython.org, then PsychoPy with `--no-deps`, then the rest of
PsychoPy's declared deps individually. See
[docs/quickstart.md](docs/quickstart.md) for what it does and why.

Optional hardware-trigger backends:

```bash
uv pip install -e ".[lsl]"           # add LSL marker stream
uv pip install -e ".[serial]"        # add serial-port triggers
uv pip install -e ".[all-triggers]"  # both
```

## CLI

```
gradcpt run [--config PATH] [--subject ID] [--session ID] [--no-probes]
            [--triggers {none,serial,parallel,lsl}] [--bids-root PATH]
            [--seed N] [--no-gui] [--probes-file PATH]
gradcpt validate-config [PATH]
gradcpt list-stimuli [--folder PATH]
```

Also runnable as `python -m gradcpt`.

## Output

Data is written in BIDS-Behavioral layout under `--bids-root`:

```
{root}/
├── dataset_description.json
├── participants.tsv
├── README
├── task-gradcpt_events.json
├── task-gradcpt_beh.json
└── sub-<id>/[ses-<id>/]beh/
    ├── sub-<id>_task-gradcpt_run-<NN>_events.tsv
    ├── sub-<id>_task-gradcpt_run-<NN>_beh.tsv
    └── sub-<id>_task-gradcpt_run-<NN>_beh.json
```

One block of trials = one BIDS run. `events.tsv` is the analysis-ready table
(trial onsets, responses, accuracy, probe responses); `_beh.tsv` is the raw
keypress log; `_beh.json` carries refresh-rate measurement, dropped-frame
summary, full config snapshot.

## Documentation

- [Quickstart + Linux PsychoPy install notes](docs/quickstart.md)
- [Configuration reference](docs/configuration.md)
- [Frame-accurate timing](docs/timing.md)
- [Triggers + codebook](docs/triggers.md)
- [BIDS output spec](docs/bids.md)
- [Response-assignment algorithm](docs/algorithm.md)
- [Developing](docs/DEVELOPING.md)

## License

MIT — see [LICENSE](LICENSE). Stimulus images are derived from the original
`gradcptpy` distribution (also MIT, 2024 David Braun).
