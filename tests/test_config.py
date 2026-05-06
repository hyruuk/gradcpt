from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest

from gradcpt.config import (
    BIDSConfig,
    Config,
    ConfigError,
    ProbeConfig,
    StimuliConfig,
    TaskConfig,
    TriggerConfig,
    WindowConfig,
    deep_merge,
    from_dict,
    load_config,
    load_yaml,
    to_plain_dict,
)


# ---------------------------------------------------------------------------
# Defaults & casting
# ---------------------------------------------------------------------------


def test_default_config_is_valid_except_subject():
    cfg = Config()
    # Subject is required, so the bare default fails validation.
    with pytest.raises(ConfigError, match="bids.subject"):
        cfg.validate()


def test_minimal_valid_config():
    cfg = Config(bids=BIDSConfig(subject="pilot01"))
    cfg.validate()  # no exception


def test_dataclass_defaults_match_documented_values():
    t = TaskConfig()
    assert (t.n_trials, t.n_blocks, t.transition_time_s, t.prop_dom) == (80, 2, 0.8, 0.9)
    assert t.dom_key == "auto"
    assert t.unambig_low == 0.4 and t.unambig_high == 0.55
    assert t.expected_refresh_rate_hz is None

    p = ProbeConfig()
    assert (p.enabled, p.next_es_min, p.next_es_max, p.isi_s) == (True, 30, 45, 0.5)

    tr = TriggerConfig()
    assert tr.backend == "none"
    assert tr.pulse_duration_s == 0.005

    s = StimuliConfig()
    assert s.flip_vertical is True
    assert s.scrambled_enabled is False

    w = WindowConfig()
    assert w.size == (1920, 1080)


def test_deep_merge_overrides_leaves_and_preserves_others():
    base = {"a": 1, "b": {"c": 2, "d": 3}, "e": [1, 2]}
    overlay = {"b": {"c": 99}, "e": [9, 9]}
    merged = deep_merge(base, overlay)
    assert merged == {"a": 1, "b": {"c": 99, "d": 3}, "e": [9, 9]}
    # base/overlay not mutated
    assert base["b"] == {"c": 2, "d": 3}
    assert overlay == {"b": {"c": 99}, "e": [9, 9]}


def test_deep_merge_introduces_new_keys():
    merged = deep_merge({"a": 1}, {"b": 2})
    assert merged == {"a": 1, "b": 2}


def test_from_dict_casts_optional_path_and_tuples():
    raw = {
        "task": {"n_trials": 40, "seed": 7},
        "window": {"size": [800, 600], "color": [0.1, 0.2, 0.3]},
        "stimuli": {"folder": "/some/where"},
        "bids": {"subject": "s1", "root": "./out", "run_index": None},
    }
    cfg = from_dict(raw, Config)
    assert cfg.task.n_trials == 40
    assert cfg.task.seed == 7
    assert cfg.window.size == (800, 600)
    assert cfg.window.color == (0.1, 0.2, 0.3)
    assert cfg.stimuli.folder == Path("/some/where")
    assert cfg.bids.run_index is None
    assert cfg.bids.root == Path("./out")


def test_from_dict_rejects_invalid_literal():
    with pytest.raises(ConfigError, match="dom_key"):
        from_dict({"task": {"dom_key": "x"}}, Config)


def test_from_dict_keeps_unset_fields_at_default():
    cfg = from_dict({"bids": {"subject": "s1"}}, Config)
    assert cfg.task.n_trials == TaskConfig().n_trials
    assert cfg.probe.enabled is True


def test_to_plain_dict_roundtrips_through_from_dict():
    cfg = Config(bids=BIDSConfig(subject="abc", root=Path("/tmp/bids")))
    plain = to_plain_dict(cfg)
    assert plain["bids"]["subject"] == "abc"
    assert plain["bids"]["root"] == "/tmp/bids"
    cfg2 = from_dict(plain, Config)
    assert cfg2.bids.subject == "abc"
    assert cfg2.bids.root == Path("/tmp/bids")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "patch,match",
    [
        ({"task": {"n_trials": 1}}, "n_trials"),
        ({"task": {"prop_dom": 0.0}}, "prop_dom"),
        ({"task": {"prop_dom": 1.5}}, "prop_dom"),
        ({"task": {"transition_time_s": 0}}, "transition_time_s"),
        ({"task": {"unambig_low": 0.6, "unambig_high": 0.5}}, "unambig"),
        ({"probe": {"next_es_min": 5, "next_es_max": 4}}, "next_es"),
        ({"probe": {"next_es_max": 999}}, "next_es_max"),
        ({"triggers": {"backend": "serial"}}, "serial_port"),
        ({"triggers": {"backend": "parallel"}}, "parallel_address"),
        ({"window": {"size": [0, 100]}}, "window.size"),
        ({"bids": {"subject": "bad-id!"}}, "BIDS"),
        ({"bids": {"session": "x.y"}}, "session"),
    ],
)
def test_validation_rejects(patch, match):
    base = {"bids": {"subject": "s1"}}
    raw = deep_merge(base, patch)
    cfg = from_dict(raw, Config)
    with pytest.raises(ConfigError, match=match):
        cfg.validate()


def test_validation_passes_with_serial_backend_and_port():
    raw = {
        "bids": {"subject": "s1"},
        "triggers": {"backend": "serial", "serial_port": "/dev/ttyACM0"},
    }
    cfg = from_dict(raw, Config)
    cfg.validate()


def test_validation_passes_with_lsl_backend():
    raw = {"bids": {"subject": "s1"}, "triggers": {"backend": "lsl"}}
    cfg = from_dict(raw, Config)
    cfg.validate()


# ---------------------------------------------------------------------------
# YAML roundtrip & merge precedence
# ---------------------------------------------------------------------------


def test_default_yaml_matches_dataclass_defaults():
    """The shipped default_config.yaml must reflect the dataclass defaults."""
    yaml_path = Path(str(files("gradcpt.data") / "default_config.yaml"))
    yaml_data = load_yaml(yaml_path)
    expected = to_plain_dict(Config())
    # bids.subject is "" in the dataclass; the YAML uses the empty string too.
    assert yaml_data == expected


def test_load_config_yaml_then_cli_then_gui_precedence(tmp_path):
    yaml_file = tmp_path / "cfg.yaml"
    yaml_file.write_text(
        "task:\n  n_trials: 50\n  n_blocks: 4\nbids:\n  subject: yamlsub\n"
    )
    cfg = load_config(
        yaml_path=yaml_file,
        cli_overrides={"task": {"n_blocks": 6}, "bids": {"subject": "clisub"}},
        gui_overrides={"bids": {"subject": "guisub"}},
    )
    # n_trials only in YAML
    assert cfg.task.n_trials == 50
    # n_blocks: YAML(4) overridden by CLI(6), no GUI value
    assert cfg.task.n_blocks == 6
    # subject: yaml < cli < gui
    assert cfg.bids.subject == "guisub"


def test_load_config_validation_fires_by_default(tmp_path):
    yaml_file = tmp_path / "bad.yaml"
    yaml_file.write_text("task:\n  prop_dom: 5\nbids:\n  subject: s1\n")
    with pytest.raises(ConfigError, match="prop_dom"):
        load_config(yaml_path=yaml_file)


def test_load_config_can_skip_validation(tmp_path):
    yaml_file = tmp_path / "bad.yaml"
    yaml_file.write_text("task:\n  prop_dom: 5\nbids:\n  subject: s1\n")
    cfg = load_config(yaml_path=yaml_file, validate=False)
    assert cfg.task.prop_dom == 5
