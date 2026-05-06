"""LSL marker-stream trigger sender.

Pushes a single string sample per event. Recording software (LabRecorder etc.)
listens to the stream and timestamps events in LSL clock space.
"""
from __future__ import annotations

import uuid

from .base import EventCodeT, TriggerSender


class LSLSender(TriggerSender):
    def __init__(self, stream_name: str, stream_type: str = "Markers"):
        try:
            import pylsl  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "LSL backend requires pylsl. Install with `pip install gradcpt[lsl]`."
            ) from e
        self._pylsl = pylsl
        self._stream_name = stream_name
        self._stream_type = stream_type
        self._info = pylsl.StreamInfo(
            stream_name,
            stream_type,
            channel_count=1,
            nominal_srate=0,
            channel_format="string",
            source_id=f"gradcpt-{uuid.uuid4().hex}",
        )
        self._outlet: object | None = None

    def open(self) -> None:
        self._outlet = self._pylsl.StreamOutlet(self._info)

    def send(self, code: EventCodeT, *, label: str | None = None) -> None:
        if self._outlet is None:
            raise RuntimeError("LSLSender.open() must be called before send()")
        payload = str(code) if label is None else f"{code}|{label}"
        self._outlet.push_sample([payload])

    def close(self) -> None:
        # pylsl outlets are cleaned up when the StreamOutlet is GC'd.
        self._outlet = None
