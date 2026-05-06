from __future__ import annotations

from pathlib import Path

import pytest

from gradcpt.cli import _cli_overrides_from_run_args, build_parser, main


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
