# Quickstart

## Install

```bash
cd gradcpt
uv venv --python 3.10
uv pip install -e ".[dev]"
```

That gets you the package, the test suite, and `gradcpt validate-config` /
`gradcpt list-stimuli`. Tests run as `uv run pytest`.

To actually run the experiment you also need PsychoPy. PsychoPy is *not*
declared as a project dependency for two reasons:

1. PsychoPy 2024.2.x declares a transitive on `pypi-search>=1.2.1`, but no
   such package has ever been published to PyPI. Any tool that resolves
   PsychoPy's full dep tree fails immediately.
2. On Linux PsychoPy's `wxPython>=4.1.1` dep only ships to PyPI as a source
   distribution, which requires `libgtk-3-dev`, `libwxgtk3.2-dev`, OpenGL
   headers, and ~30 minutes of compile time even when the headers are
   present.

Use the bundled script to install both the prebuilt wxPython wheel and
PsychoPy with the broken transitive skipped:

```bash
./scripts/install_psychopy.sh
```

What the script does:

1. Detects your distro (Ubuntu / Linux Mint → Ubuntu / Debian / Fedora).
2. Installs `wxPython==4.2.2` from
   `https://extras.wxpython.org/wxPython4/extras/linux/gtk3/<distro>/`
   (the wxPython project's own prebuilt-wheel index, not on PyPI).
3. Runs `uv pip install --no-deps psychopy==2024.2.5`.
4. Fetches PsychoPy's full dep list from PyPI's JSON API, drops
   `pypi-search` and `wxPython`, and installs the rest in a single
   `uv pip install -r` invocation.
5. Verifies `import psychopy` works.

Override versions / distro by environment variable:

```bash
PSYCHOPY_VERSION=2024.2.5 WXPYTHON_VERSION=4.2.2 \
WXPYTHON_DISTRO=ubuntu-22.04 ./scripts/install_psychopy.sh
```

Optional hardware-trigger extras (these *are* in
`[project.optional-dependencies]` since they have no broken transitives):

```bash
uv pip install -e ".[lsl]"           # LSL marker stream
uv pip install -e ".[serial]"        # serial-port triggers
uv pip install -e ".[all-triggers]"  # both LSL and serial
```

> The ``parallel`` backend uses :mod:`psychopy.parallel` and on Linux requires
> the system-level `pyparallel` setup; on Windows it needs `inpoutx64.dll`.
> See [triggers.md](triggers.md).

## Run the test suite

```bash
uv run pytest
```

The `gui` marker is excluded by default. To run GUI smoke tests on a machine
with a display:

```bash
uv run pytest -m gui
```

## Run a pilot session

```bash
uv run gradcpt run --subject pilot01 --bids-root ./bids
```

Pass `--no-gui` to skip the dialog (useful for batch / scripted runs):

```bash
uv run gradcpt run --no-gui --subject pilot01 --bids-root ./bids \
    --triggers none --seed 42
```

Override a custom config:

```bash
uv run gradcpt run --config my_config.yaml --subject pilot01
```

`my_config.yaml` only needs to specify the fields you want to override; defaults
fill in the rest. See [configuration.md](configuration.md) for the full schema.

## PsychoPy on Linux — manual fallback

If `scripts/install_psychopy.sh` fails (unusual distro, custom uv setup,
etc.), reproduce its three steps by hand:

```bash
# 1. Prebuilt wxPython wheel (replace ubuntu-24.04 with your distro)
uv pip install \
    -f https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-24.04 \
    wxPython==4.2.2

# 2. PsychoPy itself, no deps
uv pip install --no-deps psychopy==2024.2.5

# 3. PsychoPy's deps without pypi-search and wxPython (already installed)
curl -s https://pypi.org/pypi/psychopy/2024.2.5/json | \
    python3 -c "
import json, sys
d = json.load(sys.stdin)
for r in d['info']['requires_dist'] or []:
    if 'extra ==' in r: continue
    name = r.split(';')[0].split('>')[0].split('=')[0].split('<')[0].strip()
    if name in ('pypi-search', 'wxPython'): continue
    print(r)
" > /tmp/psychopy_deps.txt
uv pip install -r /tmp/psychopy_deps.txt
```

Other escape hatches:

* **Standalone PsychoPy.** Download from psychopy.org and run gradcpt against
  its bundled interpreter:
  ```bash
  /path/to/StandalonePsychoPy/python -m pip install -e .
  /path/to/StandalonePsychoPy/python -m gradcpt run --subject pilot01
  ```
* **System wxPython package.** On Debian/Ubuntu, `sudo apt install
  python3-wxgtk4.0` provides a system-level install; you can then use it
  in a venv with `--system-site-packages`.
