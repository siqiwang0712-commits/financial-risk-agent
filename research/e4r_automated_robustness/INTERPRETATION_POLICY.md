# E4-R interpretation policy

**Status: `POST_HOC_AUTOMATED_ROBUSTNESS`.** E4-R is a retrospective robustness and
competitive-baseline study. It does not confirm E4, it does not create prospective
evidence, and it is not E5.

This file fixes the interpretation rules **before any result is produced**. The thresholds
and decision rules below are applied mechanically by `e4r_report.py`; they are not chosen
after seeing the numbers, and they are not revised afterwards.

---

## 1. Vocabulary

| Term | Operational definition |
|---|---|
| `APPROX_EQ` | two AUROCs `a`, `b` with `|a − b| ≤ 0.02`, **or** a paired BCa interval for `a − b` that contains 0 |
| `BETTER` | `a − b > 0.02` **and** the paired BCa interval for `a − b` excludes 0 below |
| `TEMPORAL_GAIN` | `AUROC(B6_full) − AUROC(B6_no_temporal)`; since `B6_no_temporal` is rank-equivalent to `B0`, this equals the `B6 − B0` gain up to the score scale |
| `SINGLE_TERM_GAIN(t)` | `AUROC(B6_full) − AUROC(B6_minus_t)` |
| `MAX_SINGLE_TERM_GAIN` | the largest `SINGLE_TERM_GAIN` over the four growth terms |
| `CONCENTRATED` | `MAX_SINGLE_TERM_GAIN ≥ 0.80 × TEMPORAL_GAIN` |
| `DESTROYED` | `TEMPORAL_GAIN ≥ 0.80 × (AUROC(B6_full) − AUROC(B0))`, i.e. removing the temporal block removes at least 80% of what B6 adds over B0 |

The 0.02 equivalence band is set from the sampling scale of this cohort: the standard error
of the paired ΔAUROC is roughly 0.008, so 0.02 is about 2.5 standard errors — wide enough
that a difference inside it cannot be read as a real ordering, narrow enough that a
difference outside it is not trivially dismissible.

---

## 2. Decision cases

The cases are **not** mutually exclusive: several can fire at once, and all that fire are
reported. Nothing is suppressed because it is inconvenient.

### Case A
**If** `B6 BETTER B0` **and** `Boosting-F2 APPROX_EQ B6`:
> Temporal information adds value, but the gain is reproducible by conventional tabular
> learning; no Agent-specific interpretation follows.

### Case B
**If** `Boosting-F2 BETTER B6`:
> B6 captures useful temporal information but its hand-designed aggregation is not
> competitive with a learned nonlinear tabular baseline.

### Case C
**If** `B6 APPROX_EQ Boosting-F2` **or** `B6 BETTER Boosting-F2`:
> The transparent hand-designed temporal score remains competitive with stronger learned
> tabular baselines on this retrospective cohort.

### Case D
**If** `DESTROYED`:
> E4's gain appears materially dependent on temporal information.

### Case E
**If** `CONCENTRATED`:
> The observed B6 improvement is concentrated in a narrow temporal signal rather than
> broadly distributed across trajectory features.

### Case F
**If** any of the following instability markers fires:
- a sector clearing the `n ≥ 40 / events ≥ 10` gate where `AUROC(B6) − AUROC(B0) ≤ 0`;
- any leave-one-out deletion that reverses the sign of the observed `ΔAUROC(B6 − B0)`;
- a leave-sector-out deletion that moves `ΔAUROC(B6 − B0)` below 50% of the observed value;
- a missingness tercile where `AUROC(B6) − AUROC(B0) ≤ 0`;

> The aggregate E4 improvement is not uniformly robust across the evaluated population.

---

## 3. Phrasing clarifications, added post-hoc (they decide nothing)

These were added after the first report, alongside the hardening pass in
`EXTENSION_PROTOCOL.md`. **No threshold, no case membership and no decision rule changed**, and no
result was recomputed to accommodate them. They exist because two phrasings in the first report
could be read as stronger than the arithmetic supports.

### 3.1 The temporal block is a structural decomposition, not a causal finding

The rank-equivalence `B6_no_temporal = 0.75 × B0` is a property of a deterministic formula. It
must be written as:

> Removing the temporal block collapses B6 to a strictly rank-equivalent transformation of B0;
> therefore all B6–B0 ranking separation is mechanically introduced through the temporal
> component.

It must **not** be written as:

> temporal variables causally explain 100% of the gain.

The decomposition says where the reordering comes from inside B6's own arithmetic. It says nothing
about causation, and nothing about the informational content of the underlying variables.

### 3.2 Case F's sector marker now requires interval support

The original marker fired on a negative point estimate. A point estimate from 68 observations with
14 events is not a finding. The marker now fires when:

- a gated sector's bootstrap interval for ΔAUROC lies entirely below zero; **or**
- a gated sector's point estimate is negative and its interval spans zero — in which case the
  marker is worded as a point-estimate loss the data cannot confirm.

This makes Case F strictly harder to fire than before. It was tightened so that a small sector is
not read as a sector failure.

### 3.3 Intervals condition on the realized out-of-fold predictions

Every reported DeLong and bootstrap interval treats each observation's out-of-fold score as fixed.
It therefore **does not fully integrate training-procedure uncertainty**. `model_stability.json`
measures that omitted component separately under repeated nested cross-validation; it is
descriptive and does not enter any primary comparison.

---

## 4. What is *not* claimed

- No p-value here is a confirmatory test of E4. Primary comparisons are Holm-corrected
  within the prespecified family, but the study remains `POST_HOC`.
- Subgroup results are descriptive. They constrain E5's design; they do not license a
  subgroup claim.
- Coefficients reported in the incremental test are prediction-time associations fitted on
  4/5 of the cohort, not causal effects.
- Calibration numbers are descriptive. Scores stay `UNCALIBRATED`.
- The threshold sweep is `SENSITIVITY_ONLY`. It does not select an operating point and must
  not be used to change the production configuration.
- If the leakage audit returns `CONFIRMED_LEAKAGE`, the study is `INVALIDATED` and this
  policy file is not applied at all.

---

## 5. Failure discipline

- `NOT_ESTIMABLE` is written wherever a quantity cannot be supported by the data. It is
  never replaced by an optimistic estimate.
- No model is dropped for performing badly. No sector is dropped for looking unfavourable.
- `experiment_config.json` is frozen before the first formal run; if it changes afterwards
  the pipeline aborts. The post-hoc hardening additions live in `extension_config.json` and
  cannot move that hash.
