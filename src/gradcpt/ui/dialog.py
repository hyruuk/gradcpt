"""GUI dialog seeded from a config dict (PsychoPy)."""
from __future__ import annotations

from typing import Any

# Fields shown in the GUI (everything else stays YAML-only).
GUI_FIELDS: tuple[tuple[str, str, str], ...] = (
    # (label, dotted-path-into-config-dict, hint)
    ("subject", "bids.subject", "Required. Alphanumeric only."),
    ("session", "bids.session", "Optional. Alphanumeric only or blank."),
    ("dom_key", "task.dom_key", "auto, j, or f."),
    ("triggers_backend", "triggers.backend", "none, serial, parallel, or lsl."),
    ("probes_enabled", "probe.enabled", "true / false."),
    ("n_trials", "task.n_trials", "Trials per block."),
    ("n_blocks", "task.n_blocks", "Number of blocks."),
    ("bids_root", "bids.root", "Output root directory."),
)


def _get_path(d: dict, path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        cur = cur[part]
    return cur


def _set_path(d: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur[p]
    cur[parts[-1]] = value


def show_dialog(seeded: dict, *, title: str = "GradCPT — session info") -> dict | None:
    """Show a PsychoPy dialog seeded from ``seeded``.

    Returns a dict of GUI-side overrides (only the changed fields), or
    ``None`` if the user cancelled. The returned dict is suitable for
    passing as ``gui_overrides`` to :func:`gradcpt.config.load_config`.
    """
    from psychopy import gui  # imported lazily

    seed_dict: dict[str, Any] = {}
    for label, path, _ in GUI_FIELDS:
        val = _get_path(seeded, path)
        if val is None:
            seed_dict[label] = ""
        elif isinstance(val, bool):
            seed_dict[label] = val
        else:
            seed_dict[label] = str(val)

    dlg = gui.DlgFromDict(
        dictionary=seed_dict,
        title=title,
        order=[label for label, _, _ in GUI_FIELDS],
        tip={label: hint for label, _, hint in GUI_FIELDS},
    )
    if not dlg.OK:
        return None

    overrides: dict[str, Any] = {}
    for label, path, _ in GUI_FIELDS:
        raw = seed_dict[label]
        coerced = _coerce(raw, path)
        _set_path_create(overrides, path, coerced)
    return overrides


def _coerce(value: Any, path: str) -> Any:
    """Coerce GUI string values back to their config types."""
    if path in ("task.n_trials", "task.n_blocks"):
        return int(value)
    if path == "probe.enabled":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "1", "yes"}
    if path == "bids.session":
        return str(value).strip() or None
    return str(value)


def _set_path_create(d: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
