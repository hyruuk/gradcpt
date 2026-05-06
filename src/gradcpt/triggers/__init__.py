"""Pluggable hardware-trigger backends.

Use :func:`make_sender` to construct the right backend from a
:class:`gradcpt.config.TriggerConfig`. All concrete senders share the
:class:`TriggerSender` Protocol — the runner only ever talks to that interface.
"""
from __future__ import annotations

from ..config import TriggerConfig
from .base import EventCode, NoopSender, TriggerSender


def make_sender(cfg: TriggerConfig) -> TriggerSender:
    """Construct the configured trigger backend.

    Lazy import per backend so that optional hardware libs (pyserial, pylsl)
    are only required when their backend is selected.
    """
    if cfg.backend == "none":
        return NoopSender()
    if cfg.backend == "serial":
        if not cfg.serial_port:
            raise ValueError("triggers.backend='serial' requires triggers.serial_port")
        from .serial_sender import SerialSender

        return SerialSender(
            port=cfg.serial_port,
            baud=cfg.serial_baud,
            pulse_duration_s=cfg.pulse_duration_s,
        )
    if cfg.backend == "parallel":
        if cfg.parallel_address is None:
            raise ValueError("triggers.backend='parallel' requires triggers.parallel_address")
        from .parallel_sender import ParallelSender

        return ParallelSender(
            address=cfg.parallel_address,
            pulse_duration_s=cfg.pulse_duration_s,
        )
    if cfg.backend == "lsl":
        from .lsl_sender import LSLSender

        return LSLSender(
            stream_name=cfg.lsl_stream_name,
            stream_type=cfg.lsl_stream_type,
        )
    raise ValueError(f"unknown trigger backend: {cfg.backend!r}")


__all__ = ["TriggerSender", "NoopSender", "make_sender", "EventCode"]
