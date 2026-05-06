"""Command-line interface for gradcpt."""
from __future__ import annotations

import argparse
import logging
import sys
from importlib.resources import files
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, load_config, to_plain_dict
from .stimuli import bundled_stimuli_root, list_images


log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gradcpt", description="Run the GradCPT task.")
    p.add_argument("--version", action="version", version=f"gradcpt {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    # gradcpt run
    run = sub.add_parser("run", help="Run an experimental session.")
    run.add_argument("--config", type=Path, help="Path to YAML config (overrides defaults).")
    run.add_argument("--subject", type=str, help="Subject label (required if --no-gui).")
    run.add_argument("--session", type=str)
    run.add_argument("--no-probes", action="store_true", help="Disable experience-sampling probes.")
    run.add_argument("--triggers", choices=["none", "serial", "parallel", "lsl"])
    run.add_argument("--bids-root", type=Path)
    run.add_argument("--seed", type=int)
    run.add_argument("--no-gui", action="store_true", help="Skip the GUI dialog.")
    run.add_argument("--probes-file", type=Path, help="Override probe items YAML.")
    run.add_argument("-v", "--verbose", action="count", default=0)

    # gradcpt validate-config
    vc = sub.add_parser("validate-config", help="Validate a YAML config file.")
    vc.add_argument("path", type=Path, nargs="?", help="YAML path; default = bundled default_config.yaml.")

    # gradcpt list-stimuli
    ls = sub.add_parser("list-stimuli", help="Print bundled stimulus image paths.")
    ls.add_argument("--folder", type=Path, help="Use this folder instead of the bundled assets.")
    ls.add_argument("--category", type=str, help="Limit output to a category subfolder.")

    return p


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 1:
        level = logging.INFO
    if verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s | %(message)s")


def _cli_overrides_from_run_args(args: argparse.Namespace) -> dict:
    """Translate CLI flags to the config-dict path overrides."""
    out: dict = {}
    if args.subject is not None:
        out.setdefault("bids", {})["subject"] = args.subject
    if args.session is not None:
        out.setdefault("bids", {})["session"] = args.session or None
    if args.no_probes:
        out.setdefault("probe", {})["enabled"] = False
    if args.triggers is not None:
        out.setdefault("triggers", {})["backend"] = args.triggers
    if args.bids_root is not None:
        out.setdefault("bids", {})["root"] = str(args.bids_root)
    if args.seed is not None:
        out.setdefault("task", {})["seed"] = args.seed
    if args.probes_file is not None:
        out.setdefault("probe", {})["items_file"] = str(args.probes_file)
    return out


def _cmd_run(args: argparse.Namespace) -> int:
    cli_overrides = _cli_overrides_from_run_args(args)

    if args.no_gui:
        if not args.subject:
            print("--subject is required with --no-gui", file=sys.stderr)
            return 2
        cfg = load_config(yaml_path=args.config, cli_overrides=cli_overrides)
    else:
        # Build pre-GUI dict, show GUI, then re-load with GUI overrides.
        pre_cfg = load_config(yaml_path=args.config, cli_overrides=cli_overrides, validate=False)
        try:
            from .ui.dialog import show_dialog  # imports psychopy
        except ImportError as e:
            print(
                f"PsychoPy is required for the GUI dialog. "
                f"Install with `pip install gradcpt[run]` or pass --no-gui. ({e})",
                file=sys.stderr,
            )
            return 3
        gui_overrides = show_dialog(to_plain_dict(pre_cfg))
        if gui_overrides is None:
            print("Cancelled by user.", file=sys.stderr)
            return 1
        cfg = load_config(
            yaml_path=args.config, cli_overrides=cli_overrides, gui_overrides=gui_overrides
        )

    # Defer importing runner (psychopy) until we're ready to actually run.
    try:
        from .runner import run_experiment
    except ImportError as e:  # pragma: no cover
        print(
            f"PsychoPy is required to run the experiment. "
            f"Install with `pip install gradcpt[run]`. ({e})",
            file=sys.stderr,
        )
        return 3
    run_experiment(cfg)
    return 0


def _cmd_validate_config(args: argparse.Namespace) -> int:
    path = args.path
    if path is None:
        path = Path(str(files("gradcpt.data") / "default_config.yaml"))
    try:
        # The default YAML has subject="" which fails validation; allow that
        # specifically if validating the bundled default.
        cfg = load_config(yaml_path=path, validate=False)
        if not cfg.bids.subject and path == Path(str(files("gradcpt.data") / "default_config.yaml")):
            print(f"OK (defaults): {path} (subject is '' as expected for the bundled default)")
            return 0
        cfg.validate()
    except ConfigError as e:
        print(f"INVALID: {path}\n  {e}", file=sys.stderr)
        return 1
    print(f"OK: {path}")
    return 0


def _cmd_list_stimuli(args: argparse.Namespace) -> int:
    root = args.folder if args.folder is not None else bundled_stimuli_root()
    categories = (
        [args.category] if args.category else [p.name for p in sorted(root.iterdir()) if p.is_dir()]
    )
    for cat in categories:
        folder = root / cat
        if not folder.is_dir():
            print(f"# {cat}: (folder missing at {folder})")
            continue
        print(f"# {cat}")
        for p in list_images(folder):
            print(p)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(getattr(args, "verbose", 0))
    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "validate-config":
        return _cmd_validate_config(args)
    if args.cmd == "list-stimuli":
        return _cmd_list_stimuli(args)
    parser.print_help()
    return 2
