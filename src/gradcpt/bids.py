"""BIDS-Behavioral output writer.

Layout (one block of GradCPT trials = one BIDS run)::

    {root}/
    ├── dataset_description.json
    ├── participants.tsv / .json
    ├── README
    ├── task-gradcpt_events.json
    ├── task-gradcpt_beh.json
    └── sub-<id>/[ses-<id>/]beh/
        ├── sub-<id>[_ses-<id>]_task-gradcpt_run-NN_events.tsv
        ├── sub-<id>[_ses-<id>]_task-gradcpt_run-NN_beh.tsv
        └── sub-<id>[_ses-<id>]_task-gradcpt_run-NN_beh.json

Writes are atomic (write to a sibling ``.tmp`` then ``os.replace``). The writer
flushes both per-block files at the end of each block, so a crash mid-experiment
leaves any completed block's data intact and the in-progress block's empty.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from . import __version__ as PACKAGE_VERSION
from .codebook import CODEBOOK_VERSION, code_levels, codebook_dict
from .config import Config
from .reconcile import ResolvedTrial
from .responses import KeyPressLog


log = logging.getLogger(__name__)


EVENT_COLUMNS: tuple[str, ...] = (
    "onset",
    "duration",
    "trial_type",
    "stim_category",
    "stim_id",
    "response",
    "response_time",
    "coherence_at_press",
    "accuracy",
    "ambiguous",
    "probe_id",
    "item_name",
    "item_response",
    "n_dropped_in_trial",
    "block_idx",
    "trial_idx",
)


@dataclass
class EventRow:
    """One row in events.tsv. Unset fields are written as ``n/a``."""

    onset: float
    duration: float
    trial_type: str
    stim_category: str | None = None
    stim_id: str | None = None
    response: str | None = None
    response_time: float | None = None
    coherence_at_press: float | None = None
    accuracy: int | None = None
    ambiguous: bool | None = None
    probe_id: int | None = None
    item_name: str | None = None
    item_response: float | None = None
    n_dropped_in_trial: int | None = None
    block_idx: int | None = None
    trial_idx: int | None = None


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _bids_label_re() -> re.Pattern[str]:
    return re.compile(r"^[A-Za-z0-9]+$")


def _check_label(label: str, *, name: str) -> None:
    if not _bids_label_re().match(label):
        raise ValueError(f"BIDS {name} label {label!r} is not [A-Za-z0-9]+")


def subject_dir(root: Path, subject: str, session: str | None) -> Path:
    _check_label(subject, name="subject")
    out = Path(root) / f"sub-{subject}"
    if session is not None:
        _check_label(session, name="session")
        out = out / f"ses-{session}"
    return out / "beh"


def run_filename_stem(
    subject: str, session: str | None, task: str, run_idx: int
) -> str:
    parts = [f"sub-{subject}"]
    if session is not None:
        parts.append(f"ses-{session}")
    parts.append(f"task-{task}")
    parts.append(f"run-{run_idx:02d}")
    return "_".join(parts)


def auto_run_idx(beh_dir: Path, subject: str, task: str) -> int:
    """Return the next free run index by scanning existing files."""
    if not beh_dir.is_dir():
        return 1
    pat = re.compile(rf"^sub-{re.escape(subject)}.*_task-{re.escape(task)}_run-(\d+)_events\.tsv$")
    indices: list[int] = []
    for p in beh_dir.iterdir():
        m = pat.match(p.name)
        if m:
            indices.append(int(m.group(1)))
    return (max(indices) + 1) if indices else 1


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class BIDSWriter:
    """Per-block BIDS writer.

    One instance per execution. Use :meth:`begin_block` at the start of each
    block, :meth:`append_event` / :meth:`append_keypress` during, and
    :meth:`end_block` at the end. :meth:`finalize` writes the dataset-level
    sidecars and the participants table.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.root = Path(cfg.bids.root)
        self.subject = cfg.bids.subject
        self.session = cfg.bids.session
        self.task = cfg.bids.task_label
        self.beh_dir = subject_dir(self.root, self.subject, self.session)
        self._explicit_run = cfg.bids.run_index
        self._next_auto_run: int | None = None
        # Per-block buffers (cleared at begin_block)
        self._events: list[EventRow] = []
        self._keypress_log: KeyPressLog = KeyPressLog()
        self._frame_summary: dict | None = None
        self._refresh_meas: dict | None = None
        self._dom_key: str | None = None
        self._seed: int | None = None
        self._current_block: int | None = None
        self._current_run_idx: int | None = None
        # Per-execution metadata
        self._frame_summaries: list[dict] = []
        self._block_run_map: list[tuple[int, int]] = []  # (block_idx, run_idx)

    # ----- Lifecycle --------------------------------------------------------

    def begin_block(self, block_idx: int) -> int:
        """Start a new block. Returns the BIDS run-NN index assigned to it."""
        self._events.clear()
        self._keypress_log = KeyPressLog()
        self._frame_summary = None
        self._current_block = block_idx
        self._current_run_idx = self._resolve_run_index()
        self._block_run_map.append((block_idx, self._current_run_idx))
        self.beh_dir.mkdir(parents=True, exist_ok=True)
        return self._current_run_idx

    def append_event(self, row: EventRow) -> None:
        self._events.append(row)

    def append_resolved_trial(self, trial: ResolvedTrial, *, onset: float, duration: float, n_dropped: int = 0) -> None:
        """Convenience: convert a :class:`ResolvedTrial` to an :class:`EventRow`."""
        trial_type = "gradcpt_dom_trial" if trial.condition == "dom" else "gradcpt_nondom_trial"
        if trial.condition == "scrambled":
            trial_type = "gradcpt_scrambled_trial"
        self.append_event(
            EventRow(
                onset=onset,
                duration=duration,
                trial_type=trial_type,
                stim_category=trial.condition,
                stim_id=trial.image_id,
                response=trial.response_key,
                response_time=trial.rt_s,
                coherence_at_press=None,
                accuracy=trial.accuracy,
                ambiguous=trial.ambiguous,
                probe_id=None,
                item_name=None,
                item_response=None,
                n_dropped_in_trial=n_dropped,
                block_idx=self._current_block,
                trial_idx=trial.trial_idx,
            )
        )

    def append_keypress(self, kp_record) -> None:  # noqa: ANN001
        self._keypress_log.append(kp_record)

    def set_block_metadata(
        self,
        *,
        frame_summary: dict | None = None,
        refresh_meas: dict | None = None,
        dom_key: str | None = None,
        seed: int | None = None,
    ) -> None:
        if frame_summary is not None:
            self._frame_summary = frame_summary
        if refresh_meas is not None:
            self._refresh_meas = refresh_meas
        if dom_key is not None:
            self._dom_key = dom_key
        if seed is not None:
            self._seed = seed

    def end_block(self) -> None:
        """Atomically write events.tsv, beh.tsv, and beh.json for this block."""
        if self._current_run_idx is None:
            raise RuntimeError("end_block() called without begin_block()")
        stem = run_filename_stem(self.subject, self.session, self.task, self._current_run_idx)
        events_path = self.beh_dir / f"{stem}_events.tsv"
        beh_path = self.beh_dir / f"{stem}_beh.tsv"
        beh_json_path = self.beh_dir / f"{stem}_beh.json"

        if events_path.exists():
            log.warning("Overwriting existing run file %s", events_path)

        _atomic_write_text(events_path, self._render_events_tsv())
        _atomic_write_text(beh_path, self._render_beh_tsv())
        _atomic_write_text(beh_json_path, json.dumps(self._render_beh_json(), indent=2) + "\n")

        if self._frame_summary is not None:
            self._frame_summaries.append({"block_idx": self._current_block, **self._frame_summary})

        # Reset per-block state
        self._current_run_idx = None
        self._current_block = None
        self._frame_summary = None

    def finalize(self) -> None:
        """Write dataset-level sidecars / participants table / README."""
        self.root.mkdir(parents=True, exist_ok=True)
        _write_dataset_description(self.root)
        _write_task_events_json(self.root, self.task)
        _write_task_beh_json(self.root, self.task, self.cfg)
        _write_readme(self.root)
        _append_participant(self.root, self.subject, self._dom_key)

    # ----- Sanity checks ----------------------------------------------------

    def sanity_check(self) -> None:
        """Light validation: required files exist, events sorted, no NaN onsets."""
        if not self.beh_dir.is_dir():
            raise FileNotFoundError(f"BIDS beh dir missing: {self.beh_dir}")
        for block_idx, run_idx in self._block_run_map:
            stem = run_filename_stem(self.subject, self.session, self.task, run_idx)
            events_path = self.beh_dir / f"{stem}_events.tsv"
            if not events_path.is_file():
                raise FileNotFoundError(f"missing events file for block {block_idx}: {events_path}")
            df = pd.read_csv(events_path, sep="\t")
            if df["onset"].isna().any():
                raise ValueError(f"NaN onset in {events_path}")
            if not (df["onset"].diff().dropna() >= -1e-9).all():
                raise ValueError(f"events.tsv onsets not sorted in {events_path}")

    # ----- Internals --------------------------------------------------------

    def _resolve_run_index(self) -> int:
        if self._explicit_run is not None:
            # Explicit run + auto-increment per block: use explicit for the
            # first block, then continue incrementing.
            if self._next_auto_run is None:
                self._next_auto_run = self._explicit_run + 1
                return self._explicit_run
            run = self._next_auto_run
            self._next_auto_run += 1
            return run
        if self._next_auto_run is None:
            self._next_auto_run = auto_run_idx(self.beh_dir, self.subject, self.task)
        run = self._next_auto_run
        self._next_auto_run += 1
        return run

    def _render_events_tsv(self) -> str:
        if not self._events:
            return "\t".join(EVENT_COLUMNS) + "\n"
        rows = [asdict(e) for e in self._events]
        df = pd.DataFrame(rows, columns=list(EVENT_COLUMNS))
        return df.to_csv(sep="\t", index=False, na_rep="n/a")

    def _render_beh_tsv(self) -> str:
        df = self._keypress_log.to_dataframe()
        return df.to_csv(sep="\t", index=False, na_rep="n/a")

    def _render_beh_json(self) -> dict:
        from .config import to_plain_dict

        out: dict = {
            "TaskName": "GradCPT",
            "GradcptVersion": PACKAGE_VERSION,
            "CodebookVersion": CODEBOOK_VERSION,
            "RunIndex": self._current_run_idx,
            "BlockIndex": self._current_block,
            "DomKey": self._dom_key,
            "Seed": self._seed,
            "ConfigSnapshot": to_plain_dict(self.cfg),
        }
        if self._refresh_meas is not None:
            out["RefreshRateMeasured"] = self._refresh_meas
        if self._frame_summary is not None:
            out["FrameIntervalSummary"] = self._frame_summary
        return out


# ---------------------------------------------------------------------------
# Top-level files
# ---------------------------------------------------------------------------


def _write_dataset_description(root: Path) -> None:
    path = root / "dataset_description.json"
    payload = {
        "Name": "GradCPT",
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "License": "MIT",
        "Authors": ["GradCPT contributors"],
        "Acknowledgements": (
            "Original GradCPT task by Esterman et al. (2013); PsychoPy Builder "
            "implementation by David Braun (gradcptpy)."
        ),
        "GeneratedBy": [
            {
                "Name": "gradcpt",
                "Version": PACKAGE_VERSION,
                "CodebookVersion": CODEBOOK_VERSION,
            }
        ],
    }
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            existing = {}
        existing.update(payload)
        payload = existing
    _atomic_write_text(path, json.dumps(payload, indent=2) + "\n")


def _write_task_events_json(root: Path, task: str) -> None:
    path = root / f"task-{task}_events.json"
    payload: dict = {
        "TaskName": "GradCPT",
        "TaskDescription": (
            "Gradual-onset continuous performance task (Esterman et al., 2013). "
            "Participants press a key for go (city) trials and withhold for "
            "no-go (mountain) trials; stimuli fade gradually into one another."
        ),
        "onset": {"Description": "Onset time relative to the start of the run.", "Units": "s"},
        "duration": {"Description": "Duration of the event.", "Units": "s"},
        "trial_type": {
            "Description": "Type of event.",
            "Levels": {
                "gradcpt_dom_trial": "Onset of a city (go / dominant) trial.",
                "gradcpt_nondom_trial": "Onset of a mountain (no-go / non-dominant) trial.",
                "gradcpt_scrambled_trial": "Onset of a scrambled-scene trial (when enabled).",
                "block_start": "Start of a GradCPT block.",
                "block_end": "End of a GradCPT block.",
                "probe_start": "Start of an experience-sampling probe.",
                "probe_item": "An experience-sampling slider item is shown.",
                "probe_submit": "Enter pressed for a probe item.",
                "probe_end": "End of an experience-sampling probe.",
            },
        },
        "stim_category": {
            "Description": "Category of the stimulus image.",
            "Levels": {"dom": "city", "nondom": "mountain", "scrambled": "phase-scrambled scene"},
        },
        "stim_id": {"Description": "Image filename stem."},
        "response": {"Description": "Key pressed (or n/a)."},
        "response_time": {
            "Description": "Time from trial onset to keypress (post reconciliation).",
            "Units": "s",
        },
        "coherence_at_press": {
            "Description": "Coherence of the current trial at the moment the keypress occurred (0=fully prior image, 1=fully current image)."
        },
        "accuracy": {"Description": "1 if correct (press for go, no press for no-go); 0 otherwise."},
        "ambiguous": {"Description": "True if the press fell in the ambiguous coherence band and was reconciled by neighbor context."},
        "probe_id": {"Description": "Sequential probe number within the run."},
        "item_name": {"Description": "Name of the experience-sampling item."},
        "item_response": {"Description": "Slider value in [0, 1] for the experience-sampling item."},
        "n_dropped_in_trial": {"Description": "Number of frames in this trial that exceeded the refresh threshold."},
        "block_idx": {"Description": "0-indexed block number within the execution."},
        "trial_idx": {"Description": "1-indexed trial number within the block."},
        "Codebook": codebook_dict(),
        "CodebookDescriptions": code_levels(),
    }
    _atomic_write_text(path, json.dumps(payload, indent=2) + "\n")


def _write_task_beh_json(root: Path, task: str, cfg: Config) -> None:
    path = root / f"task-{task}_beh.json"
    payload = {
        "TaskName": "GradCPT",
        "Description": "Raw keypress log (every press, never deduplicated).",
        "Columns": {
            "timestamp_global_s": "Time of keypress in PsychoPy core clock.",
            "timestamp_trial_relative_s": "Time of keypress relative to current trial onset (s).",
            "block_idx": "0-indexed block number.",
            "trial_idx": "1-indexed trial within block.",
            "trial_condition": "dom or nondom.",
            "image_id": "Filename stem of the trial's stimulus.",
            "coherence_at_press": "Coherence of current trial when key was pressed.",
            "frame_idx_in_trial": "Frame index within the trial (0-based).",
            "key": "Key pressed.",
            "provisional_assigned_trial": "Online provisional trial assignment.",
            "provisional_assignment_kind": "previous, current, or ambiguous.",
            "rt_to_press_s": "Time from current trial onset flip to key tDown (s).",
        },
        "ReconciliationParameters": {
            "unambig_low": cfg.task.unambig_low,
            "unambig_high": cfg.task.unambig_high,
            "benefit_of_doubt_for_nogo": cfg.task.benefit_of_doubt_for_nogo,
        },
    }
    _atomic_write_text(path, json.dumps(payload, indent=2) + "\n")


def _write_readme(root: Path) -> None:
    path = root / "README"
    if path.exists():
        return
    text = (
        "GradCPT — gradual-onset continuous performance task\n"
        "===================================================\n\n"
        "Participants press a key for city (go) scenes and withhold their\n"
        "response for mountain (no-go) scenes. Scenes gradually transition\n"
        "from one to the next via per-pixel linear interpolation over\n"
        "~800 ms (configurable). Optional experience-sampling probes appear\n"
        "every 30–45 trials (configurable).\n\n"
        "One block of trials = one BIDS run. See task-gradcpt_events.json\n"
        "and task-gradcpt_beh.json for column descriptions.\n"
    )
    _atomic_write_text(path, text)


def _append_participant(root: Path, subject: str, dom_key: str | None) -> None:
    pt_tsv = root / "participants.tsv"
    pt_json = root / "participants.json"
    if pt_tsv.exists():
        df = pd.read_csv(pt_tsv, sep="\t")
    else:
        df = pd.DataFrame(columns=["participant_id", "dom_key"])
    pid = f"sub-{subject}"
    if pid in set(df["participant_id"].astype(str)):
        return  # already present
    new_row = {"participant_id": pid, "dom_key": dom_key or "n/a"}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    _atomic_write_text(pt_tsv, df.to_csv(sep="\t", index=False, na_rep="n/a"))

    if not pt_json.exists():
        json_payload = {
            "participant_id": {"Description": "Unique participant identifier (sub-<label>)."},
            "dom_key": {"Description": "Dominant-response key used in this session ('j' or 'f')."},
        }
        _atomic_write_text(pt_json, json.dumps(json_payload, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_text(path: Path, content: str) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
