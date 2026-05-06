# Response-to-trial reconciliation

Why this is hard: GradCPT presents a continuous fade between adjacent images,
so a key press is not unambiguously associated with a trial. A press at
50 % coherence could plausibly belong to either the previous or the current
image. The original gradcptpy distribution solved this with a post-hoc R
script (`process_data/response_assignment.r`). We've ported that algorithm
to pure Python in `gradcpt.reconcile`, with configurable thresholds and
explicit ambiguity flags so analysts know which trials needed disambiguation.

## Algorithm

For each press in the raw `_beh.tsv`:

### Pass 1 — preliminary classification by coherence

Let `c = coherence_at_press` and `T = current_trial_idx`.

```
if c < unambig_low:    candidate ← T - 1  (previous trial)
elif c > unambig_high: candidate ← T      (current trial)
else:                  candidate ← AMBIGUOUS  (deferred)
```

Defaults: `unambig_low = 0.4`, `unambig_high = 0.55`.

### Pass 2 — resolve ambiguous presses by neighbor context

For each press still marked AMBIGUOUS:

1. Check whether the previous trial (`T-1`) and current trial (`T`) already
   have presses assigned by some other (non-ambiguous) press in pass 1.
2. If exactly one is unassigned, assign this press to that trial.
3. If neither is assigned:
   - If `benefit_of_doubt_for_nogo == True` and the current trial is
     `nondom`, assign to the previous trial. (Intuition: the participant
     correctly withheld on the no-go; the press belongs to the prior go
     trial.)
   - Otherwise, assign to the current trial.
4. If both are already assigned, assign to the current trial (will be
   deduplicated below).

### Pass 3 — deduplicate

If multiple presses landed on the same trial after passes 1–2, keep the
**fastest** one (smallest `rt_to_press_s`). The losing presses are
discarded *for the events.tsv* but remain in the raw `_beh.tsv` log.

### Pass 4 — build resolved trial rows

For every trial in the plan:

```
response_key = (kept press's key) or None
rt           = (kept press's rt_to_press_s) or None
ambiguous    = (kept press's coherence was in the ambiguous band)
reassigned   = (kept press's native trial != this trial's idx)

if reassigned and this trial == kept_press.trial_idx - 1:
    rt += transition_time_s     # press was clocked against the *next* trial's onset

if condition == "dom":
    accuracy = 1 if rt is not None else 0
else:  # nondom (or scrambled-as-nogo)
    accuracy = 1 if rt is None else 0
```

The `+ transition_time_s` adjustment mirrors the original R algorithm
(line 131 of `response_assignment.r`).

## Differences from the R script

* **Language**: Python vs R. No external dependency on R or `dplyr`.
* **Configurable thresholds**: `unambig_low` / `unambig_high` are set in
  the YAML config (R hard-codes 0.4 / 0.55).
* **Configurable benefit-of-doubt**: the original always pushes ambiguous
  no-go presses back; we expose `benefit_of_doubt_for_nogo`.
* **Online + offline**: each press is annotated *online* with a provisional
  trial assignment, so the raw `_beh.tsv` is interpretable without re-running
  reconciliation. The `events.tsv` carries the resolved final answer.
* **Ambiguity flag**: every reconciled trial row has explicit `ambiguous`
  and `reassigned` columns so downstream filters can exclude or count these
  trials.

## Equivalence

`tests/test_reconcile.py` covers each algorithm branch with a synthetic
input. Each test states the input scenario in plain English, runs
`reconcile()`, and asserts the resolved trial rows. Together these confirm
that the Python port reproduces the R algorithm's branch behavior.

For added insurance, `tests/test_reconcile_golden.py` (planned for
follow-up) will compare bit-for-bit against hand-derived expected outputs
for a small fixture set, providing regression protection against future
algorithm changes.
