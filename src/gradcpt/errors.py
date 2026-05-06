"""Custom exceptions raised by the runtime."""
from __future__ import annotations


class ExperimentInterrupted(KeyboardInterrupt):
    """Raised when the participant or experimenter aborts the run.

    Inherits from :class:`KeyboardInterrupt` so a bare ``except
    KeyboardInterrupt`` catches both Ctrl+C and an Esc-key abort with the
    same handler.
    """
