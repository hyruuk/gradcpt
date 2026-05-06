# Developing

## Setup

```bash
cd gradcpt
uv venv --python 3.10
uv pip install -e ".[dev]"
source .venv/bin/activate
```

You don't need PsychoPy for the test suite — only the runtime modules
(`runner.py`, `routines/*`, `ui/dialog.py`) import it, and they do so lazily.

## Tests

```bash
pytest                    # all non-GUI tests
pytest -m gui             # only GUI smoke tests (require display)
pytest tests/test_reconcile.py -v
pytest --cov=src/gradcpt  # with coverage
```

The full non-GUI suite runs in <1 s and has ~150 tests covering:

* `config` — YAML round-trip, validation, merge precedence
* `codebook` — uniqueness, JSON round-trip, level descriptions
* `sequencing` — proportions, no-consecutive-identical, determinism
* `stimuli` — load, mask, normalize, flip
* `transitions` — double-buffered linspace, frame indexing
* `timing` — refresh-rate math, drop summaries
* `triggers` — protocol shape, NoopSender, monkeypatched serial/lsl
* `responses` — KeyPressLog, provisional assignment thresholds
* `reconcile` — every branch of the response-assignment algorithm
* `bids` — paths, run-NN auto-increment, atomic writes, multi-block
* `probes` — scheduling, item ordering with fixed-position
* `cli` — argument parsing, validate-config, list-stimuli

## Lint / type-check

```bash
ruff check src tests
mypy src
```

(`ruff` and `mypy` are in the `[dev]` extra.)

## Adding a feature

1. Pick the module that owns the change. Each module has *one* reason to
   change (see `architecture.md`).
2. Write the test first (or alongside). Tests in this repo are short,
   parametrized, and named for the behavior they assert.
3. Update the relevant doc in `docs/` if user-visible.
4. If you change a config field, regenerate `default_config.yaml` and run
   `pytest tests/test_config.py::test_default_yaml_matches_dataclass_defaults`.
5. Bump `__version__` in `src/gradcpt/__init__.py` for any non-trivial
   change. The version is recorded in every BIDS sidecar.

## Module dependency graph

```
config ────────────────────┐
codebook ──────┐           │
               ├─ triggers │
sequencing ────┤           │
               │           │
stimuli ───────┤           │
transitions ───┤           │
timing ────────┤           │
               ├─→ runner ─┘
responses ─────┤    │
reconcile ─────┤    └─→ cli + ui/dialog
probes ────────┤    │
bids ──────────┤    │
routines/ ─────┘    │
```

`routines/*` imports PsychoPy. Everything else is pure Python.

## Release

1. Update `__version__` and `CHANGELOG.md`.
2. `git tag v0.X.Y`, `git push --tags`.
3. (Future) build wheel via `uv build` and publish.
