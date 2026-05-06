# Quickstart

## Install

```bash
cd gradcpt
uv venv --python 3.10
uv pip install -e ".[dev]"
source .venv/bin/activate
```

That gets you the package, the test suite, and `gradcpt validate-config` /
`gradcpt list-stimuli`. To actually run the experiment you also need PsychoPy:

```bash
uv pip install -e ".[dev,run]"
```

Optional hardware extras:

```bash
uv pip install -e ".[run,lsl]"           # LSL marker stream
uv pip install -e ".[run,serial]"        # serial-port triggers
uv pip install -e ".[run,all-triggers]"  # both LSL and serial
```

> The ``parallel`` backend uses :mod:`psychopy.parallel` and on Linux requires
> the system-level `pyparallel` setup; on Windows it needs `inpoutx64.dll`.
> See [triggers.md](triggers.md).

## Run the test suite

```bash
pytest
```

The `gui` marker is excluded by default. To run GUI smoke tests on a machine
with a display:

```bash
pytest -m gui
```

## Run a pilot session

```bash
gradcpt run --subject pilot01 --bids-root ./bids
```

Pass `--no-gui` to skip the dialog (useful for batch / scripted runs):

```bash
gradcpt run --no-gui --subject pilot01 --bids-root ./bids \
    --triggers none --seed 42
```

Override a custom config:

```bash
gradcpt run --config my_config.yaml --subject pilot01
```

`my_config.yaml` only needs to specify the fields you want to override; defaults
fill in the rest. See [configuration.md](configuration.md) for the full schema.

## PsychoPy on Linux — known pain

PsychoPy pins relatively old versions of `wxpython`, `pyglet`, `glfw`, etc.,
which can clash with recent NumPy and other packages. If `uv pip install
psychopy` fails to resolve cleanly:

1. **Use the bundled standalone PsychoPy** (download from psychopy.org) and run
   gradcpt against its interpreter:
   ```bash
   /path/to/StandalonePsychoPy/python -m pip install -e .
   /path/to/StandalonePsychoPy/python -m gradcpt run --subject pilot01
   ```
2. **Loose-resolve PsychoPy**:
   ```bash
   uv pip install psychopy --no-deps
   uv pip install wxpython pyglet pillow pyqt5 glfw pyparsing python-bidi requests
   ```
3. **Use uv's `--resolution=lowest-direct`** to honor PsychoPy's transitive pin
   requests:
   ```bash
   uv pip install -e ".[run]" --resolution=lowest-direct
   ```

The package itself doesn't try to solve PsychoPy's dependency tree — that's a
moving target outside our scope.
