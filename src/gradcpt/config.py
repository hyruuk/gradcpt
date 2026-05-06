"""Configuration schema and loader.

Frozen dataclasses describe the runtime configuration. Values can come from
(in increasing precedence): built-in defaults, a YAML file, CLI overrides, and
a GUI dialog. ``load_config`` orchestrates the merge and runs ``validate``.

The configuration is intentionally agnostic of PsychoPy — this module is
importable without any optional dependency installed.
"""
from __future__ import annotations

import dataclasses as _dc
import types
import typing as _t
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args, get_origin, get_type_hints

import yaml


class ConfigError(ValueError):
    """Raised when the configuration is malformed or contradictory."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskConfig:
    n_trials: int = 80
    n_blocks: int = 2
    transition_time_s: float = 0.8
    prop_dom: float = 0.9
    # If None, the measured refresh rate is logged and used as-is; no
    # cross-check is performed. Set to e.g. 60.0 (or 120.0 for a 120 Hz
    # monitor) to catch the "ran on the wrong screen" failure mode.
    expected_refresh_rate_hz: float | None = None
    refresh_rate_tolerance_hz: float = 2.0
    refresh_rate_abort_tolerance_hz: float = 5.0
    dom_key: Literal["j", "f", "auto"] = "auto"
    log_extra_keys: bool = True
    seed: int | None = None
    unambig_low: float = 0.4
    unambig_high: float = 0.55
    benefit_of_doubt_for_nogo: bool = True


@dataclass(frozen=True)
class ProbeConfig:
    enabled: bool = True
    next_es_min: int = 30
    next_es_max: int = 45
    isi_s: float = 0.5
    submit_key: str = "return"
    items_file: Path | None = None
    initial_mouse_jitter: float = 0.05
    initial_mouse_y: float = -0.4


@dataclass(frozen=True)
class TriggerConfig:
    backend: Literal["none", "serial", "parallel", "lsl"] = "none"
    serial_port: str | None = None
    serial_baud: int = 115200
    parallel_address: int | None = None
    lsl_stream_name: str = "gradcpt-events"
    lsl_stream_type: str = "Markers"
    pulse_duration_s: float = 0.005


@dataclass(frozen=True)
class StimuliConfig:
    folder: Path | None = None
    scrambled_enabled: bool = False
    scrambled_role: Literal["distractor", "extra_nogo", "extra_go"] = "distractor"
    image_size_px: int = 256
    apply_circular_mask: bool = True
    flip_vertical: bool = True
    normalize_to_minus1_plus1: bool = True
    # Drawn size in PsychoPy "height" units (1.0 = full screen height,
    # both axes). At 0.5 the stimulus is half the screen height tall and
    # the same in width — a square (and circular after masking) regardless
    # of the screen's aspect ratio.
    display_size: float = 0.5


@dataclass(frozen=True)
class WindowConfig:
    fullscreen: bool = True
    size: tuple[int, int] = (1920, 1080)
    monitor_name: str = "testMonitor"
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    units: str = "norm"
    screen: int = 0
    record_frame_intervals: bool = True


@dataclass(frozen=True)
class BIDSConfig:
    root: Path = Path("./bids")
    subject: str = ""
    session: str | None = None
    task_label: str = "gradcpt"
    run_index: int | None = None
    write_validator_report: bool = False


@dataclass(frozen=True)
class Config:
    task: TaskConfig = field(default_factory=TaskConfig)
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    triggers: TriggerConfig = field(default_factory=TriggerConfig)
    stimuli: StimuliConfig = field(default_factory=StimuliConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    bids: BIDSConfig = field(default_factory=BIDSConfig)

    def validate(self) -> None:
        """Raise :class:`ConfigError` on the first violated invariant."""
        t = self.task
        if t.n_trials < 2:
            raise ConfigError("task.n_trials must be >= 2")
        if t.n_blocks < 1:
            raise ConfigError("task.n_blocks must be >= 1")
        if not 0 < t.prop_dom < 1:
            raise ConfigError("task.prop_dom must be in (0, 1)")
        if t.transition_time_s <= 0:
            raise ConfigError("task.transition_time_s must be > 0")
        if t.expected_refresh_rate_hz is not None and t.expected_refresh_rate_hz <= 0:
            raise ConfigError("task.expected_refresh_rate_hz must be > 0 when set")
        if not (0.0 <= t.unambig_low < t.unambig_high <= 1.0):
            raise ConfigError("require 0 <= task.unambig_low < task.unambig_high <= 1")

        p = self.probe
        if p.enabled:
            if p.next_es_min < 1 or p.next_es_max < p.next_es_min:
                raise ConfigError("require 1 <= probe.next_es_min <= probe.next_es_max")
            if p.next_es_max >= t.n_trials:
                raise ConfigError(
                    "probe.next_es_max must be < task.n_trials so a probe can fit in a block"
                )
            if p.isi_s < 0:
                raise ConfigError("probe.isi_s must be >= 0")

        tr = self.triggers
        if tr.backend == "serial" and not tr.serial_port:
            raise ConfigError("triggers.backend='serial' requires triggers.serial_port")
        if tr.backend == "parallel" and tr.parallel_address is None:
            raise ConfigError("triggers.backend='parallel' requires triggers.parallel_address")
        if tr.pulse_duration_s < 0:
            raise ConfigError("triggers.pulse_duration_s must be >= 0")

        s = self.stimuli
        if s.image_size_px < 8:
            raise ConfigError("stimuli.image_size_px must be >= 8")
        if not 0 < s.display_size <= 2:
            raise ConfigError("stimuli.display_size must be in (0, 2]")

        w = self.window
        if w.size[0] <= 0 or w.size[1] <= 0:
            raise ConfigError("window.size must be positive")
        if w.screen < 0:
            raise ConfigError("window.screen must be >= 0")

        b = self.bids
        if not b.subject:
            raise ConfigError("bids.subject is required (non-empty string)")
        if not _is_bids_label(b.subject):
            raise ConfigError(
                f"bids.subject={b.subject!r} must match BIDS label format ([A-Za-z0-9]+)"
            )
        if b.session is not None and not _is_bids_label(b.session):
            raise ConfigError(
                f"bids.session={b.session!r} must match BIDS label format ([A-Za-z0-9]+)"
            )
        if b.run_index is not None and b.run_index < 1:
            raise ConfigError("bids.run_index must be >= 1 if provided")


def _is_bids_label(s: str) -> bool:
    return bool(s) and all(c.isalnum() for c in s)


# ---------------------------------------------------------------------------
# Loader / merge
# ---------------------------------------------------------------------------


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file into a plain dict."""
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"YAML at {path} must be a mapping at the top level")
    return data


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursive dict merge. Returns a new dict; inputs are not mutated."""
    out: dict[str, Any] = {}
    for k, v in base.items():
        if k in overlay and isinstance(v, dict) and isinstance(overlay[k], dict):
            out[k] = deep_merge(v, overlay[k])
        elif k in overlay:
            out[k] = overlay[k]
        else:
            out[k] = v
    for k, v in overlay.items():
        if k not in base:
            out[k] = v
    return out


def from_dict(data: dict[str, Any], cls: type = Config) -> Any:
    """Cast a dict to a (possibly nested) frozen dataclass instance."""
    if not _dc.is_dataclass(cls):
        raise ConfigError(f"{cls.__name__} is not a dataclass")
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in _dc.fields(cls):
        if f.name not in data:
            continue
        kwargs[f.name] = _cast_value(data[f.name], hints[f.name], path=f.name)
    return cls(**kwargs)


def _cast_value(value: Any, typ: Any, *, path: str) -> Any:
    if value is None:
        return None
    origin = get_origin(typ)
    args = get_args(typ)

    # Optional[X] / Union[..., None]
    if origin in (_t.Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _cast_value(value, non_none[0], path=path)
        # Try each in order; raise if all fail
        last_err: Exception | None = None
        for a in non_none:
            try:
                return _cast_value(value, a, path=path)
            except Exception as e:  # noqa: BLE001
                last_err = e
        raise ConfigError(f"{path}: could not cast value {value!r} to any of {non_none}") from last_err

    # Literal[...]
    if origin is Literal:
        if value not in args:
            raise ConfigError(f"{path}: value {value!r} not in allowed {args}")
        return value

    # Tuples
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise ConfigError(f"{path}: expected sequence, got {type(value).__name__}")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_cast_value(v, args[0], path=f"{path}[*]") for v in value)
        if len(args) != len(value):
            raise ConfigError(f"{path}: expected {len(args)} elements, got {len(value)}")
        return tuple(_cast_value(v, t, path=f"{path}[{i}]") for i, (v, t) in enumerate(zip(value, args)))

    # Lists
    if origin is list:
        if not isinstance(value, (list, tuple)):
            raise ConfigError(f"{path}: expected list, got {type(value).__name__}")
        return [_cast_value(v, args[0] if args else Any, path=f"{path}[*]") for v in value]

    # Path
    if typ is Path:
        return value if isinstance(value, Path) else Path(value)

    # Nested dataclass
    if _dc.is_dataclass(typ):
        if not isinstance(value, dict):
            raise ConfigError(f"{path}: expected mapping for {typ.__name__}, got {type(value).__name__}")
        return from_dict(value, typ)

    # Primitive — accept as-is (yaml gives us int/float/str/bool already)
    return value


def to_plain_dict(cfg: Any) -> dict[str, Any]:
    """Recursively convert a (nested) dataclass to a YAML-serializable dict.

    Path → str, tuple → list, Enum → name. Other primitives untouched.
    """
    if _dc.is_dataclass(cfg):
        out: dict[str, Any] = {}
        for f in _dc.fields(cfg):
            out[f.name] = to_plain_dict(getattr(cfg, f.name))
        return out
    if isinstance(cfg, Path):
        return str(cfg)
    if isinstance(cfg, tuple):
        return [to_plain_dict(v) for v in cfg]
    if isinstance(cfg, list):
        return [to_plain_dict(v) for v in cfg]
    if isinstance(cfg, dict):
        return {k: to_plain_dict(v) for k, v in cfg.items()}
    return cfg


def load_config(
    yaml_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
    *,
    gui_overrides: dict[str, Any] | None = None,
    validate: bool = True,
) -> Config:
    """Build a :class:`Config` by layering defaults < YAML < CLI < GUI.

    ``gui_overrides`` is the dict returned by the GUI dialog *after* it has
    been seeded with the post-CLI dict — the runner is responsible for
    showing the dialog and passing the result here.
    """
    raw = to_plain_dict(Config())
    if yaml_path is not None:
        raw = deep_merge(raw, load_yaml(Path(yaml_path)))
    if cli_overrides:
        raw = deep_merge(raw, cli_overrides)
    if gui_overrides:
        raw = deep_merge(raw, gui_overrides)
    cfg = from_dict(raw, Config)
    if validate:
        cfg.validate()
    return cfg
