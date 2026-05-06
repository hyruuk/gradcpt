from __future__ import annotations

import json

from gradcpt.codebook import CODEBOOK_VERSION, EventCode, code_levels, codebook_dict


def test_event_code_values_unique_and_positive():
    values = [int(c) for c in EventCode]
    assert all(v > 0 for v in values)
    assert len(values) == len(set(values)), "EventCode values must be unique"


def test_codebook_dict_roundtrips_through_json():
    payload = json.dumps(codebook_dict())
    restored = json.loads(payload)
    assert restored == codebook_dict()


def test_codebook_version_string():
    assert CODEBOOK_VERSION == "1"


def test_code_levels_cover_every_event_code():
    levels = code_levels()
    for c in EventCode:
        assert c.name in levels, f"Missing description for {c.name}"
        assert levels[c.name], f"Empty description for {c.name}"


def test_event_code_member_lookup():
    assert EventCode["BLOCK_START"] == EventCode.BLOCK_START
    assert int(EventCode.TRIAL_ONSET_DOM) == 20
