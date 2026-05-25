from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from gradcpt.cli import (
    _cli_overrides_from_run_args,
    _inject_quick_if_no_subcommand,
    build_parser,
    main,
)


def test_parser_run_minimal():
    p = build_parser()
    args = p.parse_args(["run", "--subject", "s1"])
    assert args.cmd == "run"
    assert args.subject == "s1"
    assert args.no_gui is False


def test_parser_run_full():
    p = build_parser()
    args = p.parse_args(
        [
            "run",
            "--config",
            "/tmp/cfg.yaml",
            "--subject",
            "s1",
            "--session",
            "01",
            "--no-probes",
            "--triggers",
            "lsl",
            "--bids-root",
            "/tmp/bids",
            "--seed",
            "42",
            "--no-gui",
        ]
    )
    assert args.config == Path("/tmp/cfg.yaml")
    assert args.session == "01"
    assert args.no_probes is True
    assert args.triggers == "lsl"
    assert args.bids_root == Path("/tmp/bids")
    assert args.seed == 42
    assert args.no_gui is True


def test_parser_validate_config_optional_path():
    p = build_parser()
    args = p.parse_args(["validate-config"])
    assert args.path is None


def test_parser_list_stimuli():
    p = build_parser()
    args = p.parse_args(["list-stimuli"])
    assert args.folder is None
    assert args.category is None


def test_parser_invalid_trigger_choice():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["run", "--subject", "s1", "--triggers", "ftdi"])


def test_cli_overrides_from_run_args_translates_paths_correctly():
    args = build_parser().parse_args(
        [
            "run",
            "--subject",
            "s1",
            "--session",
            "01",
            "--no-probes",
            "--triggers",
            "lsl",
            "--bids-root",
            "/tmp/bids",
            "--seed",
            "7",
            "--no-gui",
        ]
    )
    overrides = _cli_overrides_from_run_args(args)
    assert overrides == {
        "bids": {"subject": "s1", "session": "01", "root": "/tmp/bids"},
        "probe": {"enabled": False},
        "triggers": {"backend": "lsl"},
        "task": {"seed": 7},
    }


def test_run_no_gui_without_subject_fails(capsys):
    rc = main(["run", "--no-gui"])
    assert rc == 2
    out = capsys.readouterr()
    assert "subject" in out.err.lower()


def test_validate_config_default_yaml_passes(capsys):
    rc = main(["validate-config"])
    out = capsys.readouterr()
    assert rc == 0
    assert "OK" in out.out


def test_validate_config_user_yaml_passes_when_valid(tmp_path, capsys):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("bids:\n  subject: s1\n")
    rc = main(["validate-config", str(cfg_path)])
    out = capsys.readouterr()
    assert rc == 0
    assert "OK" in out.out


def test_validate_config_user_yaml_fails_when_invalid(tmp_path, capsys):
    cfg_path = tmp_path / "bad.yaml"
    cfg_path.write_text("bids:\n  subject: s1\ntask:\n  prop_dom: 5\n")
    rc = main(["validate-config", str(cfg_path)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "INVALID" in err


def test_list_stimuli_default_prints_paths(capsys):
    rc = main(["list-stimuli"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "# city" in out
    assert "# mountain" in out
    assert ".jpg" in out


def test_list_stimuli_with_category_filter(capsys):
    rc = main(["list-stimuli", "--category", "city"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "# city" in out
    assert "# mountain" not in out


# ---------------------------------------------------------------------------
# Bare-mode (``gradcpt`` with no subcommand) routing
# ---------------------------------------------------------------------------


def test_inject_quick_when_no_subcommand_empty():
    assert _inject_quick_if_no_subcommand([]) == ["quick"]


def test_inject_quick_when_no_subcommand_only_flags():
    assert _inject_quick_if_no_subcommand(["--no-gui"]) == ["quick", "--no-gui"]
    assert _inject_quick_if_no_subcommand(["--subject", "s1"]) == [
        "quick",
        "--subject",
        "s1",
    ]


def test_inject_quick_passthrough_known_subcommands():
    for cmd in ("run", "validate-config", "list-stimuli", "quick"):
        argv = [cmd, "--subject", "s1"]
        assert _inject_quick_if_no_subcommand(list(argv)) == argv


def test_inject_quick_passthrough_version_and_help():
    assert _inject_quick_if_no_subcommand(["--version"]) == ["--version"]
    assert _inject_quick_if_no_subcommand(["--help"]) == ["--help"]
    assert _inject_quick_if_no_subcommand(["-h"]) == ["-h"]


def test_bare_with_subject_parses_as_quick():
    parser = build_parser()
    # Mirror what main() does to argv before parse_args.
    argv = _inject_quick_if_no_subcommand(["--subject", "pilot01"])
    args = parser.parse_args(argv)
    assert args.cmd == "quick"
    assert args.subject == "pilot01"
    # quick subparser does not expose --no-probes (use full ``run`` for that)
    assert not hasattr(args, "no_probes") or args.no_probes is False
    assert not hasattr(args, "probes_file") or args.probes_file is None


def test_quick_no_gui_without_subject_fails_when_no_config(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)  # ensure no ./config.yaml in the way
    rc = main(["--no-gui"])
    assert rc == 2
    assert "subject" in capsys.readouterr().err.lower()


def test_quick_creates_config_yaml_from_template(tmp_path, monkeypatch):
    """First-time bare run with --no-gui --subject seeds ./config.yaml."""
    monkeypatch.chdir(tmp_path)
    cfg_path = tmp_path / "config.yaml"
    assert not cfg_path.exists()

    with patch("gradcpt.runner.run_experiment") as mock_run:
        rc = main(["--no-gui", "--subject", "pilot01"])

    assert rc == 0
    assert cfg_path.exists()
    # Run was invoked once with a valid Config.
    assert mock_run.call_count == 1
    cfg = mock_run.call_args[0][0]
    assert cfg.bids.subject == "pilot01"
    # Template default: probes off.
    assert cfg.probe.enabled is False
    # Saved file strips per-session fields.
    import yaml as _yaml
    saved = _yaml.safe_load(cfg_path.read_text())
    assert saved["bids"]["subject"] == ""
    assert saved["bids"]["session"] is None
    assert saved["task"]["seed"] is None
    assert saved["probe"]["enabled"] is False


def test_quick_reuses_existing_config_yaml(tmp_path, monkeypatch):
    """Second-time bare run loads the saved config without overwriting params."""
    monkeypatch.chdir(tmp_path)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "task:\n  n_trials: 50\n  n_blocks: 3\n"
        "probe:\n  enabled: true\n  next_es_min: 10\n  next_es_max: 20\n"
        "bids:\n  subject: ''\n  session: null\n"
    )

    with patch("gradcpt.runner.run_experiment") as mock_run:
        rc = main(["--no-gui", "--subject", "pilot02"])

    assert rc == 0
    cfg = mock_run.call_args[0][0]
    assert cfg.task.n_trials == 50
    assert cfg.task.n_blocks == 3
    # Probes were explicitly enabled in the file → respected, not forced off.
    assert cfg.probe.enabled is True
    assert cfg.bids.subject == "pilot02"


def test_quick_with_explicit_config_errors_if_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "nope.yaml"
    rc = main(["--no-gui", "--config", str(missing), "--subject", "s1"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err.lower()
