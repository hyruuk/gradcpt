"""Serial-port trigger sender.

Writes a single byte per event to a serial device. Optionally schedules a
``\\x00`` clear after ``pulse_duration_s`` so the next event registers as a
fresh edge on hardware that requires explicit pulse widths.
"""
from __future__ import annotations

import threading

from .base import EventCodeT, TriggerSender


class SerialSender(TriggerSender):
    def __init__(self, port: str, baud: int = 115200, pulse_duration_s: float = 0.005):
        try:
            import serial as _serial  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "Serial backend requires pyserial. Install with `pip install gradcpt[serial]`."
            ) from e
        self._serial_mod = _serial
        self._port_name = port
        self._baud = baud
        self._pulse_s = pulse_duration_s
        self._dev: object | None = None
        self._timer: threading.Timer | None = None

    def open(self) -> None:
        self._dev = self._serial_mod.Serial(self._port_name, self._baud, timeout=0)

    def send(self, code: EventCodeT, *, label: str | None = None) -> None:
        if self._dev is None:
            raise RuntimeError("SerialSender.open() must be called before send()")
        byte = bytes([int(code) & 0xFF])
        self._dev.write(byte)
        if self._pulse_s > 0:
            # Schedule clear (zero byte) after pulse_duration_s.
            self._cancel_pending_clear()
            self._timer = threading.Timer(self._pulse_s, self._clear)
            self._timer.daemon = True
            self._timer.start()

    def _clear(self) -> None:
        if self._dev is not None:
            try:
                self._dev.write(b"\x00")
            except Exception:  # pragma: no cover - best-effort cleanup
                pass

    def _cancel_pending_clear(self) -> None:
        if self._timer is not None and self._timer.is_alive():
            self._timer.cancel()
        self._timer = None

    def close(self) -> None:
        self._cancel_pending_clear()
        if self._dev is not None:
            try:
                self._dev.close()
            finally:
                self._dev = None
