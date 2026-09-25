# E4-R study protocol — automated robustness and competitive baselines

**Status: `POST_HOC_AUTOMATED_ROBUSTNESS`**

E4-R is a retrospective (`POST_HOC`) study run on data that E4 has already published. It is
**not** `ESTABLISHED_E4`, **not** `CONFIRMATORY`, **not** `PROSPECTIVE`, and **not** an
`E5_RESULT`. Its only purpose is to understand E4 well enough to design E5.

> Goal. On E4's published, reproducible data, systematically test the robustness of the B6
> temporal signal and determine whether simple or strong tabular machine-learning methods,
> given the same information, can explain, reproduce or exceed B6's predictive ability.

---

## 0. Non-negotiable constraints

1. No frozen E4 artifact is modified, regenerated or repaired.
2. E4's threshold, label definition and cohort are not re-tuned to improve any result.
3. `experiment_config.json` is frozen before the first formal run and verified thereafter.
4. Any quantity that the data cannot support is reported as `NOT_ESTIMABLE`.
5. If the leakage audit returns confirmed leakage, the study is `INVALIDATED` and no
   performance conclusion is published.
6. No human judgement enters the loop: every number in the outputs is computed by
   `run_e4r.py` from the published packet.

---

## 1. Data source

`research/e4_statistical_audit/replication/` — the E4-S replication packet:

`features.json.gz`, `numeric_predictions.json`, `outcomes.json`, `analysis.json`,
`cohort.json`, `manifest.json`, plus the pipeline's own reports.

Before any analysis:

1. `manifest.json` is verified against the bytes on disk (SHA-256, every file);
2. the frozen E4 artifact manifest is verified (proving E4-R did not mutate E4);
3. the existing E4-S verifier is executed (`verify_audit.py --quick`, output redirected to a
   scratch path inside the E4-R directory so the committed E4-S artifact is untouched);
4. B0 and B6 are **reconstructed** from the packet's own metrics using the frozen scoring
   functions and checked against the published scores (tolerance 1e-9, which absorbs the
   packet's 10-decimal rounding).

If integrity fails, E4-R stops immediately. Nothing is auto-repaired.

**Analysis cohort:** outcome rows with `label_status == VERIFIED`. Expected `n = 675`,
`events = 235`. One observation per company, so company-clustering is exact.

---

## 2. Research questions

| # | Question | Section |
|---|---|---|
| R1 | Is B6 stably better than B0? | §3 |
| R2 | Does B6's gain actually come from temporal information? | §4 |
| R3 | Can strong tabular baselines reproduce or exceed B6? | §5–§7 |
| R4 | Is the result robust to subgroup, influence and missingness perturbations? | §9–§11 |
| R5 | Is the pipeline free of leakage and does it behave under negative controls? | §12–§13 |

---

## 3. R1 — replication sanity check (not a new finding)

Reproduce on the 675-row cohort:

- B0 AUROC and PR-AUC, B6 AUROC and PR-AUC, ΔAUROC, ΔPR-AUC;
- paired DeLong (DeLong, DeLong & Clarke-Pearson 1988);
- 20,000-replicate company-cluster paired BCa bootstrap;
- agreement with the published E4-S `replication_crosscheck.json`.

Statistical primitives are **imported** from `research/e4_statistical_audit/e4s_stats.py`,
not re-implemented, so E4-R's inference is continuous with the audit it builds on.

---

## 4. R2 — temporal ablation

B6's definition is **discovered from the frozen code object**, not assumed:

```
B6 = min(1, 0.75 * B0 + 0.25 * adverse / observed)
B0 = mean of the static binary checks actually observed
adverse/observed over: revenue_growth ≤ −0.10, operating_cash_flow_growth ≤ −0.25,
                       total_debt_growth ≥ 0.20, cash_growth ≤ −0.20
```

Variants (all rebuilt from the frozen closed form; no weight is refitted because B6 has
none):

| Variant | Definition |
|---|---|
| `B6_full` | the frozen score |
| `B6_no_temporal` | `0.75 × B0`, every growth term removed |
| `B6_temporal_only` | `adverse / observed`, the temporal block alone |
| `B6_minus_revenue` / `_minus_OCF` / `_minus_debt` / `_minus_cash` | the closed form with that term removed from numerator **and** denominator |

Reported per variant: AUROC, PR-AUC, ΔAUROC vs B0, ΔAUROC vs B6_full, paired DeLong and a
20,000-replicate paired BCa bootstrap.

**Structural caveat, reported not hidden:** `B6_no_temporal = 0.75 × B0` is a strictly
increasing map of B0, so `AUROC(B6_no_temporal)` equals `AUROC(B0)` *exactly*. The temporal
block is the only component that can reorder observations.

---

## 5. Baselines

| ID | Model |
|---|---|
| M0 | `LogisticRegression(penalty=None)` |
| M1 | `LogisticRegression` with L1 (liblinear) and L2 (lbfgs); C selected in the inner loop |
| M2 | `RandomForestClassifier` — explicitly **secondary** |
| M3 | `HistGradientBoostingClassifier` — prespecified nonlinear challenger |

XGBoost is **not** used: the repository ships no numpy/scipy/scikit-learn runtime, and
adding XGBoost would introduce a second heavy dependency for no capability the study needs.
This is the substitution the protocol allows.

---

## 6. Feature families

| Family | Contents | Role |
|---|---|---|
| F0 | the five B0 inputs: `current_ratio, debt_to_assets, net_margin, cfo_to_net_income, fcf_margin` | primary |
| F1 | the four B6 growth terms: `revenue_growth, operating_cash_flow_growth, total_debt_growth, cash_growth` | primary |
| F2 | F0 ∪ F1 — everything B6 can see | primary |
| F3 | every engineered metric in the packet, with a **within-fold** availability filter (≥ 0.4 coverage on the outer-training rows) | secondary exploratory |

F3 never alters the primary reading. `feature_sets.json` records the discovered fields.

---

## 7. Nested cross-validation

- **Outer:** `StratifiedGroupKFold(5, shuffle=True, random_state=20260925)`, grouped on
  `masked_company_id`, stratified on the label.
- **Inner:** `StratifiedGroupKFold(5, ...)` on the outer **training portion only**, scoring
  AUROC.
- **Preprocessing:** `SimpleImputer(median, add_indicator=True) → StandardScaler`, fitted
  inside each fold.

Forbidden and checked: preprocessing fitted on all 675 rows before CV; hyperparameter
changes made after inspecting outer-test performance; feature selection on the full cohort.

All reported metrics for learned models come from **out-of-fold** predictions. Training
performance is never reported as a result.

---

## 8. Prespecified comparisons

| ID | Comparison | Role |
|---|---|---|
| P1 | B6 vs B0 | primary |
| P2 | Logistic-F2 vs B6 | primary (linear challenger) |
| P3 | Boosting-F2 vs B6 | primary (nonlinear challenger) |

Holm step-down across the three. Membership is fixed in `experiment_config.json` and is
**not** decided by looking at outer-test results. Secondary comparisons (regularised
logistic, random forest, F3 variants, static-only logistic, and the temporal increment) are
reported unadjusted and carry no confirmatory weight.

---

## 9. Subgroup and robustness analyses

- **Sector:** gate `n ≥ 40` **and** `events ≥ 10`. All sectors clearing the gate are shown;
  the rest are `NOT_ESTIMABLE`. No favourable filtering.
- **Firm size:** tertiles of `current.total_assets` — a feature-side measure, so the split
  cannot use the outcome. If the measure were badly missing the analysis would be skipped
  and marked `NOT_ESTIMABLE`.
- **Missingness:** the fraction of F2 fields missing per observation, split into
  low/medium/high terciles.
- **Thresholds:** grid `{0.30, 0.40, 0.50, 0.60, 0.70}`; recall, specificity, precision, F1,
  FNR and review load. Marked `SENSITIVITY_ONLY` — this never selects an operating point.
- **Bootstrap stability:** 20,000 replicates; the full ΔAUROC distribution is reported
  (median, 2.5/25/75/97.5 percentiles, and `P(Δ > 0, 0.01, 0.02, 0.03)`), not just a
  p-value.
- **Influence:** leave-one-observation-out over all 675 rows and leave-one-sector-out over
  the gated sectors; only the already-public observation IDs and sectors are retained.

---

## 10. Negative controls

- **NC1 — label permutation:** 200 replicates. A sanity check that the machinery returns to
  chance under random labels. Explicitly **not** an equal-AUROC test.
- **NC2 — temporal alignment destroyed:** the four temporal columns are shuffled across
  companies; static features and labels stay put. Logistic-F2 and Boosting-F2 are re-run
  under the same (reduced) nested-CV configuration, with a real arm for comparison. A real
  temporal contribution should degrade. This is a robustness check, not causal inference.

---

## 11. Leakage audit

Automated checks over feature timestamps vs the prediction cutoff, outcome timestamps vs the
cutoff and the forward window, company and accession overlap, duplicate IDs, future-year
field names, outcome-derived and label-derived field names, and a perfect-separation screen
between every metric and the label. Confirmed leakage ⇒ `INVALIDATED`.

---

## 12. Calibration

All scores remain `UNCALIBRATED`. Brier, ECE (10 bins), CITL, calibration slope, number of
unique score values, zero/extreme mass and event rate by bin are reported **descriptively**.
No calibration map is fitted on the cohort and then evaluated on the same cohort.

---

## 13. Complexity

Inference/fit time, candidate count, feature requirements, dependency burden, failure rate
and deterministic reproducibility. No LLM cost is attributed: E4-R compares deterministic
and conventional ML comparators only.

---

## 14. Outputs

Everything listed in `README.md`, all generated from machine-readable artifacts. Figures are
rendered from the JSON artifacts, never from in-memory values.
