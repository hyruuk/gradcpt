"""Trigger-sender protocol and the no-op default."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..codebook import EventCode

EventCodeT = int | str


@runtime_checkable
class TriggerSender(Protocol):
    """A pluggable interface for sending event codes to recording hardware.

    Lifecycle: :meth:`open` once at experiment start, :meth:`send` per event,
    :meth:`close` once at experiment end. ``send`` is intended to be called
    from a ``win.callOnFlip`` callback so the byte transmission is aligned
    with vertical retrace.
    """

    def open(self) -> None: ...
    def send(self, code: EventCodeT, *, label: str | None = None) -> None: ...
    def close(self) -> None: ...


class NoopSender:
    """Trigger sender that does nothing. The default backend."""

    def open(self) -> None:
        return None

    def send(self, code: EventCodeT, *, label: str | None = None) -> None:
        return None

    def close(self) -> None:
        return None


__all__ = ["TriggerSender", "NoopSender", "EventCode", "EventCodeT"]
