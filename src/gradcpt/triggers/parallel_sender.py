"""Parallel-port trigger sender.

Uses :mod:`psychopy.parallel`. Schedules a clear (``setData(0)``) after
``pulse_duration_s`` so the next event registers as a fresh edge.
"""
from __future__ import annotations

import threading

from .base import EventCodeT, TriggerSender


class ParallelSender(TriggerSender):
    def __init__(self, address: int, pulse_duration_s: float = 0.005):
        try:
            from psychopy import parallel as _parallel  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "Parallel backend requires psychopy with parallel-port support. "
                "On Linux, ensure `pyparallel` is installed; on Windows, install "
                "`inpoutx64.dll`. Install gradcpt with `pip install gradcpt[run]`."
            ) from e
        self._parallel_mod = _parallel
        self._address = address
        self._pulse_s = pulse_duration_s
        self._port: object | None = None
        self._timer: threading.Timer | None = None

    def open(self) -> None:
        self._port = self._parallel_mod.ParallelPort(address=self._address)

    def send(self, code: EventCodeT, *, label: str | None = None) -> None:
        if self._port is None:
            raise RuntimeError("ParallelSender.open() must be called before send()")
        self._port.setData(int(code) & 0xFF)
        if self._pulse_s > 0:
            self._cancel_pending_clear()
            self._timer = threading.Timer(self._pulse_s, self._clear)
            self._timer.daemon = True
            self._timer.start()

    def _clear(self) -> None:
        if self._port is not None:
            try:
                self._port.setData(0)
            except Exception:  # pragma: no cover
                pass

    def _cancel_pending_clear(self) -> None:
        if self._timer is not None and self._timer.is_alive():
            self._timer.cancel()
        self._timer = None

    def close(self) -> None:
        self._cancel_pending_clear()
        if self._port is not None:
            try:
                self._port.setData(0)
            finally:
                self._port = None
