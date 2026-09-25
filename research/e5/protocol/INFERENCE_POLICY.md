# E5 Inference Policy

Status: **PROSPECTIVE — FROZEN BEFORE OUTCOME ACCESS**

This document fixes *how* E5 computes uncertainty and p-values, and — importantly —
which procedures are forbidden. It exists because E4's primary inference did not test the
hypothesis it was attached to.

---

## 1. The E4 defect being fixed

E4's P1 p-value came from `e4_evaluation.paired_permutation`, which shuffles the outcome
labels across observations while keeping each observation's `(B0 score, B6 score)` pair
fixed, then recomputes both AUROCs and takes the difference.

That procedure samples the distribution of `ΔAUROC` under

> `H0_independence`: the outcome is independent of **both** scores,

not under

> `H0_equality`: `AUROC(B6) = AUROC(B0)`.

These are different nulls, and `H0_independence` does not imply `H0_equality`. Rejecting
`H0_independence` therefore only establishes that *at least one* score carries signal; it
does not establish that B6 beats B0. The rejection is not transferable to the claim E4
attached to it.

Two further properties of the E4 run compound this:

- The published P1 p-value equals `1 / (2000 + 1)`, the minimum attainable value, so it is
  a **censored lower bound** rather than a resolved quantity: zero of 2,000 permutations
  reached the observed effect.
- The permutation null is **narrower** than the paired bootstrap distribution of the same
  statistic at E4's design point (implied SD 0.00772 versus 0.00879).

**And one property that does not compound it, recorded because the audit measured it.**
The E4-S calibration study simulated `H0_equality` at E4's design point and found the
label-shuffling design's empirical size to be 0.025 against a nominal 0.05, with power 0.930
against DeLong's 0.935. So the design is the **wrong test**, but at that design point it is
not materially miscalibrated, and E4's numerical conclusion is not affected. The
justification is what fails, not the number.

The lesson for E5 is not "the permutation test inflates error rates". It is that a
procedure which happens to be accurate at one design point has no guarantee at another, so
the primary test must target the hypothesis the study states. See
`research/e4_statistical_audit/AUDIT_REPORT.md` for the audit, its artifacts and its tests.

---

## 2. Prespecified primary inference

| Element | Specification |
|---|---|
| Estimand | `Δ_XY = AUROC(X) − AUROC(Y)` on the common evaluable cohort |
| Primary test | paired DeLong (DeLong, DeLong & Clarke-Pearson 1988) |
| Primary interval | company-cluster BCa bootstrap, 20,000 replicates, delete-one-cluster jackknife acceleration |
| Resampling unit | company (one observation per company) |
| Multiplicity | Holm step-down over the three primary hypotheses, family-wise α = 0.05 |
| Secondary metric | paired ΔPR-AUC via the same cluster bootstrap, event prevalence reported beside it |

Rationale for DeLong: it is the standard asymptotic test for two **correlated** ROC AUCs
evaluated on the same sample. It targets `H0_equality` directly, which is the hypothesis
the study states.

Rationale for the cluster bootstrap: observations are one-per-company, so the company is
the independent unit. An observation-level bootstrap would understate uncertainty.

---

## 3. Permitted secondary procedures

- **Within-observation score-swap randomization test.** Under the exchangeability null
  `H0_exch` the two score vectors are exchangeable given the outcome, which *implies*
  equal AUROCs. Rejecting `H0_exch` therefore does transfer to rejecting `H0_equality`,
  which is what makes this a valid — if conservative — permutation design. Reported as a
  robustness check, never as primary.
- **Threshold sensitivity** over 0.2–0.8. Sensitivity analysis only; never retuning.
- **Verification-propensity diagnostics.** Reported as a diagnostic of selection, never as
  a correction.

---

## 4. Forbidden procedures

1. **The label-permutation test as a test of `H0_equality`.** It may be reported *only*
   alongside an explicit statement of its own null (`H0_independence`) and with the
   censoring caveat if it lands on the p-value floor.
2. **Any p-value reported without its null stated.** Every p-value in every artifact must
   name the hypothesis it tests.
3. **Selecting a test after seeing outcomes.** The primary test is fixed here.
4. **Post-hoc threshold, weight, prompt, model, endpoint or cohort changes presented as
   primary.** Such changes make the data development data; if one is made, the comparison
   becomes `POST_HOC` and may not enter the primary inference family.
5. **Interpreting a `[0, 1]` score as a probability.** All scores are `UNCALIBRATED`.
6. **Imputing non-evaluable outcomes.** `INSUFFICIENT_DATA` stays unevaluable.

---

## 5. Reporting requirements

Every primary comparison reports:

- `n` pairs, event count, event-company count
- both marginal AUROCs with cluster-bootstrap intervals
- `ΔAUROC` with the BCa interval and the DeLong standard error
- the DeLong p-value, the Holm-adjusted p-value, and the null each one tests
- the prespecified decision rule's verdict
- coverage and attrition beside the estimate, never separated from it

Every artifact carries an explicit evidence label from:
`ESTABLISHED_E5`, `NOT_ESTABLISHED`, `EXPLORATORY_INSUFFICIENT_POWER`, `POST_HOC`,
`NOT_TESTED`, `UNCALIBRATED`.

---

## 6. Method-sensitivity rule

If the prespecified primary test and the prespecified robustness procedures disagree in
*direction*, the result is reported as `METHOD_SENSITIVE`. The most favourable method is
never selected as the headline. If they agree in direction but differ in strength, both
are reported.

---

## 7. Reproducibility requirements

- Deterministic stages must replay byte-identically from the frozen inputs.
- Stochastic stages report their stochasticity separately from their point estimates.
- Every inference artifact records: source commit, config hash, input hash, code hash,
  replicate count, seed, and the percentile convention used (nearest-rank versus linear
  interpolation — E4 used nearest-rank, which differs measurably from linear
  interpolation at 5,000 replicates).
- Monte Carlo precision is stated: with `B` replicates the simulation error of a 2.5%
  percentile is roughly `sqrt(p(1-p)/B)` divided by the local density. E5 uses 20,000
  replicates precisely so that the interval endpoints are not dominated by simulation
  noise.
