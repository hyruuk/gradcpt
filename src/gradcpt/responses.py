"""Online keypress logging and provisional trial assignment.

Per-frame keyboard polling lives in the routines layer; this module owns the
data structures for what is recorded and the threshold-based provisional
assignment logic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd


@dataclass
class KeyPressRecord:
    """A single keyboard event captured during a GradCPT block.

    Frame-relative metadata lets the offline reconciliation pass assign each
    press to the most likely trial.
    """

    timestamp_global_s: float
    timestamp_trial_relative_s: float
    block_idx: int
    trial_idx: int
    trial_condition: str
    image_id: str
    coherence_at_press: float
    frame_idx_in_trial: int
    key: str
    provisional_assigned_trial: int
    provisional_assignment_kind: str  # "previous" | "current" | "ambiguous"
    rt_to_press_s: float


def provisional_assign(
    coherence: float,
    current_trial: int,
    *,
    unambig_low: float = 0.4,
    unambig_high: float = 0.55,
) -> tuple[int, str]:
    """Assign a single press based on coherence thresholds.

    Mirrors step 1 of the R algorithm in ``response_assignment.r``.

    Returns
    -------
    (assigned_trial, kind) where kind ∈ {"previous", "current", "ambiguous"}.
    """
    if coherence < unambig_low:
        return current_trial - 1, "previous"
    if coherence > unambig_high:
        return current_trial, "current"
    return current_trial, "ambiguous"


class KeyPressLog:
    """In-memory append-only log of :class:`KeyPressRecord` events.

    Provides DataFrame export for tests and TSV writing for BIDS output.
    """

    COLUMNS: tuple[str, ...] = (
        "timestamp_global_s",
        "timestamp_trial_relative_s",
        "block_idx",
        "trial_idx",
        "trial_condition",
        "image_id",
        "coherence_at_press",
        "frame_idx_in_trial",
        "key",
        "provisional_assigned_trial",
        "provisional_assignment_kind",
        "rt_to_press_s",
    )

    def __init__(self) -> None:
        self._rows: list[KeyPressRecord] = []

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterable[KeyPressRecord]:
        return iter(self._rows)

    def append(self, record: KeyPressRecord) -> None:
        self._rows.append(record)

    def extend(self, records: Iterable[KeyPressRecord]) -> None:
        self._rows.extend(records)

    def to_dataframe(self) -> pd.DataFrame:
        if not self._rows:
            return pd.DataFrame(columns=list(self.COLUMNS))
        return pd.DataFrame([asdict(r) for r in self._rows], columns=list(self.COLUMNS))

    def to_tsv(self, path) -> None:  # noqa: ANN001
        self.to_dataframe().to_csv(path, sep="\t", index=False, na_rep="n/a")
