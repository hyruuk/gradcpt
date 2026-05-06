from __future__ import annotations

import sys
import types

import pytest

from gradcpt.codebook import EventCode
from gradcpt.config import TriggerConfig
from gradcpt.triggers import NoopSender, TriggerSender, make_sender


# ---------------------------------------------------------------------------
# Protocol & noop
# ---------------------------------------------------------------------------


def test_noop_sender_satisfies_protocol():
    s = NoopSender()
    assert isinstance(s, TriggerSender)


def test_noop_sender_methods_return_none():
    s = NoopSender()
    s.open()
    assert s.send(EventCode.BLOCK_START) is None
    assert s.send(42, label="trial=1") is None
    s.close()


def test_make_sender_default_is_noop():
    s = make_sender(TriggerConfig())
    assert isinstance(s, NoopSender)


def test_make_sender_unknown_backend_raises():
    cfg = TriggerConfig.__new__(TriggerConfig)  # bypass dataclass init for an invalid value
    object.__setattr__(cfg, "backend", "ftdi")
    object.__setattr__(cfg, "serial_port", None)
    object.__setattr__(cfg, "serial_baud", 115200)
    object.__setattr__(cfg, "parallel_address", None)
    object.__setattr__(cfg, "lsl_stream_name", "x")
    object.__setattr__(cfg, "lsl_stream_type", "Markers")
    object.__setattr__(cfg, "pulse_duration_s", 0.005)
    with pytest.raises(ValueError, match="unknown"):
        make_sender(cfg)


# ---------------------------------------------------------------------------
# Serial — monkeypatched
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_serial_module(monkeypatch):
    written: list[bytes] = []

    class FakeSerial:
        def __init__(self, port, baud, timeout=0):
            self.port = port
            self.baud = baud
            self.is_open = True

        def write(self, b):
            written.append(b)

        def close(self):
            self.is_open = False

    fake_mod = types.ModuleType("serial")
    fake_mod.Serial = FakeSerial
    monkeypatch.setitem(sys.modules, "serial", fake_mod)
    return written


def test_serial_sender_sends_byte(fake_serial_module):
    cfg = TriggerConfig(backend="serial", serial_port="/dev/null", pulse_duration_s=0)
    sender = make_sender(cfg)
    sender.open()
    sender.send(EventCode.BLOCK_START)
    sender.close()
    assert fake_serial_module == [bytes([int(EventCode.BLOCK_START)])]


def test_serial_sender_pulse_then_clear(fake_serial_module):
    import time

    cfg = TriggerConfig(backend="serial", serial_port="/dev/null", pulse_duration_s=0.01)
    sender = make_sender(cfg)
    sender.open()
    sender.send(20)
    time.sleep(0.05)  # allow the timer to fire
    sender.close()
    # First write is the code; second is the zero-byte clear.
    assert fake_serial_module[0] == bytes([20])
    assert fake_serial_module[1] == b"\x00"


def test_serial_sender_send_before_open_raises(fake_serial_module):
    cfg = TriggerConfig(backend="serial", serial_port="/dev/null", pulse_duration_s=0)
    sender = make_sender(cfg)
    with pytest.raises(RuntimeError):
        sender.send(1)


# ---------------------------------------------------------------------------
# LSL — monkeypatched
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_pylsl_module(monkeypatch):
    pushed: list[list[str]] = []

    class FakeStreamInfo:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class FakeStreamOutlet:
        def __init__(self, info):
            self.info = info

        def push_sample(self, sample):
            pushed.append(list(sample))

    fake_mod = types.ModuleType("pylsl")
    fake_mod.StreamInfo = FakeStreamInfo
    fake_mod.StreamOutlet = FakeStreamOutlet
    monkeypatch.setitem(sys.modules, "pylsl", fake_mod)
    return pushed


def test_lsl_sender_pushes_string_payload(fake_pylsl_module):
    cfg = TriggerConfig(backend="lsl", lsl_stream_name="test-stream")
    sender = make_sender(cfg)
    sender.open()
    sender.send(EventCode.TRIAL_ONSET_DOM, label="trial=1")
    sender.send(99)
    sender.close()
    assert fake_pylsl_module == [["20|trial=1"], ["99"]]


def test_lsl_sender_send_before_open_raises(fake_pylsl_module):
    cfg = TriggerConfig(backend="lsl")
    sender = make_sender(cfg)
    with pytest.raises(RuntimeError):
        sender.send(1)


# ---------------------------------------------------------------------------
# Missing-dep handling
# ---------------------------------------------------------------------------


def test_serial_backend_missing_dep_raises_clean_message(monkeypatch):
    monkeypatch.setitem(sys.modules, "serial", None)
    cfg = TriggerConfig(backend="serial", serial_port="/dev/null")
    with pytest.raises(ImportError, match="pyserial"):
        make_sender(cfg)


def test_lsl_backend_missing_dep_raises_clean_message(monkeypatch):
    monkeypatch.setitem(sys.modules, "pylsl", None)
    cfg = TriggerConfig(backend="lsl")
    with pytest.raises(ImportError, match="pylsl"):
        make_sender(cfg)
