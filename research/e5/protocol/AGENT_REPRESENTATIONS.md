# E5 Agent Representations — Definitions, Confound Surface, and A3

Status: **PROSPECTIVE — FROZEN IN THE PROTOCOL COMMIT**

---

## 1. The four representations, exactly as the frozen code builds them

`backend/finrisk/e4_agent.py::packet(row, representation)` is the single source of truth.
Restating it here so that no reader has to guess what an Agent actually sees:

| ID | Packet contents |
|---|---|
| **A0** | `case_id`, `raw_fy2024` (current facts, nulls dropped), `raw_same_filing_fy2023` |
| **A1** | `case_id`, `engineered_features` (the metrics dict, nulls dropped), `missingness` (missing key names for raw current / raw prior / metrics) |
| **A2** | A0 + A1 + `traditional_model_outputs` (Altman, Beneish, Piotroski, Ohlson: output, applicability, missing components) |

Every packet always carries `case_id`. The frozen code raises if any of
`cik`, `accession`, `ticker`, `company_name`, `outcome`, `label`, `B0`, `B2`, `B6`, `score`
appears as a key. That check is necessary but, as §2 shows, not sufficient.

Note what A1 already contains: the metrics dict includes a `{key}_growth` entry for every
metric (`metrics.py:158`), so **year-over-year deltas are already inside A1 and A2**.

---

## 2. Confound surface: the Agent already sees the baseline's entire feature set

This is the most consequential design fact about E4's structured comparison, and it was not
stated in E4's protocol.

The baselines consume the **same `row["metrics"]` dict** that A1 and A2 expose as
`engineered_features`:

- `ratio_risk_score` (B0) is the mean of five threshold breaches on `current_ratio`,
  `debt_to_assets`, `net_margin`, `cfo_to_net_income`, `fcf_margin`
  (`numeric_benchmark.py:10-27`).
- `temporal_risk_score` (B6) is `0.75 * ratio_risk_score(metrics) + 0.25 * adverse/observed`
  over exactly four growth metrics: `revenue_growth`, `operating_cash_flow_growth`,
  `total_debt_growth`, `cash_growth` (`numeric_benchmark.py:30-46`).
- `run_numeric` passes `metrics = row["metrics"]` to both
  (`e4_core.py:595`, `e4_core.py:603-604`), and its own reason codes name those same keys.

Therefore:

> **A1 and A2 packets contain every input that B0 and B6 use.**

This is not an inference from reading the code — it is measured. Recomputing each baseline
from `packet(row, "A2")["engineered_features"]` and comparing against the published scores in
`research/e4_statistical_audit/replication/numeric_predictions.json`, across all 2,000
observations of the published replication cohort:

| Baseline | Max absolute difference between recomputed and published |
|---|---:|
| B0 | `3.33e-11` |
| B6 | `3.33e-11` |

The residual is float and rounding noise — `_record` stores `round(score, 10)`. So **B0 and
B6 are exactly recoverable from the A2 packet**, for every observation. The Agent is handed
the baselines' complete input set, and could reproduce either baseline bit-for-bit.

Three consequences, all of which E5 must confront rather than inherit:

1. **A2 vs B6 is a comparison of aggregation, not of information access.** The Agent cannot
   have incremental *information* over B6, because it is given B6's inputs. Any measured
   difference is a difference in how the same numbers are combined.
2. **The Agent can recover B6 exactly.** A high H1 result is therefore *not* evidence of
   superior financial reasoning; it may be evidence of successful imitation. E4's protocol
   asserted "A2: ... no B0/B2/B6/Hybrid final score", which is true about the *score* and
   misleading about the *information*.
3. **The Hybrid `0.5*B6 + 0.5*A2` fuses two aggregations of the same inputs.** Its
   incremental value over B6 cannot come from new data; only from a different combination.

None of this makes E4 wrong. It narrows what E4's Agent results could ever have meant, and
it means E5's hypotheses need to be phrased in terms of aggregation.

---

## 3. Required diagnostic: aggregation-equivalence

Before any H1/H2 verdict is interpreted, E5 must report, on the frozen predictions:

| Diagnostic | Purpose |
|---|---|
| Spearman(Agent score, B6) | if this is very high, the Agent has largely reproduced the baseline |
| Spearman(Agent score, B0) | the same for the ratio baseline |
| R² of Agent score on `(B0, B6)` | how much of the Agent is a linear re-combination |
| share of Agent scores within ±0.05 of B6 | direct imitation rate |
| paired ΔAUROC of the Agent **against its own regression on (B0, B6)** | the residual signal the Agent carries that the baselines do not |

The last row is the important one. If the Agent's advantage disappears once `(B0, B6)` are
partialled out, then the Agent added no information — it re-weighted the baselines. That is
a legitimate but much weaker finding, and it must not be reported as "Agent reasoning adds
value".

This diagnostic is prespecified and is reported for every Agent arm. It is a
**diagnostic**, not a primary hypothesis, and it does not enter the Holm family.

---

## 4. A3 = A2 + explicit temporal trajectory

The brief allows one new representation, defined and frozen before outcome access. Its
rationale must be stated carefully, because the obvious rationale is wrong.

**Wrong rationale:** "A3 gives the Agent temporal information that A2 lacks." A2 already
contains every year-over-year delta B6 uses (§1). A3 built this way would be A2 with extra
formatting and would add nothing.

**Correct rationale:** A3 adds **horizon**. B0 and B6 see exactly two periods — the current
fiscal year and one same-filing comparative. A3 exposes a multi-year series and an explicit
trajectory structure, which is information no baseline has.

### 4.1 Required packet block

A3 = A2 plus one additional block:

```
temporal_evidence:
  fiscal_years:        [int, ...]           # ascending, >= 3 years required for A3 to qualify
  years_available:     int
  series:
    "<metric>":
      values:          [float | null, ...]  # aligned to fiscal_years; null = not reported
      years_observed:  int
      years_missing:   int
      direction:       improving | deteriorating | stable | mixed | not_comparable
      direction_basis: level | trend
  comparability:
    all_periods_full_year:     bool
    period_length_days:        [int, ...]
    restatement_present:       bool
    accounting_policy_change:  bool | null
  trajectory_class: persistent_deterioration | single_year_dip | recovery | stable | volatile | not_comparable
```

### 4.2 Rules that make A3 admissible

- **Same-accession only.** Every year in `series` must come from the same accession as the
  feature filing, exactly as E4's comparative rule requires. Pulling later filings in would
  break point-in-time integrity and would be future leakage.
- **No blended score.** `temporal_evidence` must not contain any aggregate risk score, and
  must not contain a monotone transform of B6. A machine check is specified in §6.
- **`direction` is defined on the raw series**, by a rule frozen in the protocol (for
  example: `improving` iff the last observed value improves on the first, with a dead band
  for `stable`). The rule is published, not left to the model.
- **`trajectory_class` is defined on the raw series too**, not on any risk score.
- **Missingness is explicit.** A3 must not silently drop a year; `null` plus
  `years_missing` is how absence is represented.

### 4.3 Eligibility gate

A3 is eligible **only if** the multi-period extraction exists in the frozen implementation
and its version is recorded in the protocol commit. E4's `build_features` extracts exactly
two periods (`e4_core.py:398-404`), so A3 requires a pipeline extension: multi-period
selection from the same accession, plus a `temporal_evidence` builder, plus tests.

If that extension is not implemented and frozen before the cohort is enumerated, **A3 is
ineligible and A2 is primary**. Adding A3 later would make it a post-hoc representation and
would remove it from the confirmatory family.

---

## 5. Freeze rule

- Exactly **one** of A2 or A3 is the primary Agent representation. The other, if run at all,
  is an ablation and is excluded from the primary inference family.
- A0 and A1 are secondary / diagnostic in either case.
- The primary representation, its prompt, its schema and its version are frozen in the
  protocol commit.

---

## 6. Leakage rules, including a machine-checkable one

The frozen `packet()` already rejects the keys
`cik, accession, ticker, company_name, outcome, label, B0, B2, B6, score`. E5 extends this:

1. Forbidden keys additionally include `ratio_risk_score`, `temporal_risk_score`,
   `hybrid_score`, `prediction`, `threshold`, `label_status`, `financial_deterioration_12m`,
   and any `*_score` key.
2. Forbidden **values**: the packet must not contain any value that equals a baseline score
   for that observation, nor any affine transform of one.
3. **Monotone re-derivation check (executable).** On the frozen packets, fit B6 from the
   packet's numeric fields by ordinary least squares. If the fitted `R²` is at or above a
   prespecified ceiling, the representation is a re-encoding of the baseline and must be
   reported as such rather than used as an Agent arm. The ceiling is frozen in the protocol
   commit; a value near 1.0 means the arm is an imitation by construction.
4. The `packet()` forbidden-key guard must be extended to the new key list and covered by a
   test, so a future edit cannot silently reintroduce a score field.

---

## 7. Machine-readable schemas

`representations.json` in this directory carries the same content in a form the pipeline and
the tests can consume: per-representation field lists, the forbidden key list, the
`temporal_evidence` schema, and the A3 eligibility flag (which stays `false` until the
multi-period extraction is implemented and frozen).

---

## 8. What this document changes about E5's hypotheses

`STUDY_PROTOCOL.md` §3 asks whether the Agent beats B6. With §2 in view, the honest phrasing
is:

> **H1** — Does a strong Agent, given the same feature set as B6, produce a better *ranking*
> than B6's fixed `0.75/0.25` blend with hard thresholds?

That is a question about aggregation quality. It is worth asking, and it is answerable. It is
not the question "does the Agent have better information", which for A1/A2 is false by
construction, and which A3 can only make true by adding horizon rather than re-encoding the
same two periods.
