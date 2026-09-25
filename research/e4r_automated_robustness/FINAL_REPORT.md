# E4-R — Automated Robustness & Competitive Baseline Study

**Status: `POST_HOC_AUTOMATED_ROBUSTNESS`** — git `749b5d3dd37b`, Python 3.13.14.

E4-R is a **retrospective (POST_HOC)** study run on E4's published replication data. It is **not** `ESTABLISHED_E4`, **not** `CONFIRMATORY`, **not** `PROSPECTIVE` and **not** an `E5_RESULT`. It does not modify E4, does not create confirmatory evidence, and does not replace E5. It exists to make E5 designable.

- cohort: **n = 675**, events = **235**, prevalence = **0.348**
- leakage audit: **REVIEW** (16/18 checks pass; disclosed as REVIEW, not leakage: endpoint_anchored_on_pre_cutoff_levels, missingness_indicators_carry_signal)
- primary multiplicity control: Holm across P1–P3
- bootstrap replicates: 20000
- post-hoc hardening pass: `extension_config.json` (`282811607c05155d…`), sections 4 and H1–H8 below; it refines the reading and cannot upgrade any statement to confirmatory

## 1. Headline

| scorer | AUROC | PR-AUC |
|---|---:|---:|
| B0 | 0.6791 | 0.5412 |
| B6 | 0.7054 | 0.5808 |
| logistic_F0 | 0.8274 | 0.7694 |
| logistic_F1 | 0.8045 | 0.7166 |
| logistic_F2 | 0.8190 | 0.7536 |
| logistic_l1_F2 | 0.8361 | 0.7745 |
| logistic_l2_F2 | 0.8320 | 0.7769 |
| random_forest_F2 | 0.8842 | 0.8269 |
| hist_gb_F1 | 0.8632 | 0.7762 |
| hist_gb_F2 | 0.8851 | 0.8387 |
| hist_gb_F3 | 0.8837 | 0.8412 |

**P1 (B6 − B0):** ΔAUROC = +0.0264, DeLong p = 0.00144, Holm-adjusted p = 0.00144, BCa 95% = [+0.0109, +0.0434], P(Δ>0) = 0.999

## 2. Interpretation under the pre-registered policy

**Case B.** B6 captures useful temporal information but its hand-designed aggregation is not competitive with a learned nonlinear tabular baseline.
**Case D.** E4's gain appears materially dependent on temporal information.
**Case F.** The aggregate E4 improvement is not uniformly robust across the evaluated population.
  - sector Transportation_Utilities: ΔAUROC(B6−B0) = -0.0046 but the interval [-0.0654, +0.0410] contains zero — a point-estimate loss that the data cannot confirm

## 3. The ten questions

### Q1. Does B6 > B0 still hold under re-check?
Yes. B0 AUROC = 0.6791, B6 AUROC = 0.7054, Δ = +0.0264 (BCa 95% [+0.0109, +0.0434], Holm p = 0.00144). This is a replication sanity check on E4's own data, not a new confirmation.

### Q2. Is the temporal signal really the main incremental source?
Removing the temporal block collapses B6 to a strictly rank-equivalent transformation of B0 (`B6_no_temporal = 0.75 × B0`, and the `min(1, ·)` clamp never binds on [0, 1]), so `AUROC(B6_no_temporal) = AUROC(B0) = 0.6791` **exactly**. Therefore all of the B6 − B0 ranking separation is mechanically introduced through the temporal component. This is a *structural decomposition of a deterministic formula*, not a causal empirical finding, and it is not evidence that temporal variables explain 100% of anything: the statement is about where the reordering comes from inside B6's own arithmetic.

Numerically, the temporal block moves AUROC by +0.0264 (meeting the DESTROYED criterion of ≥80% of the +0.0264 B6 − B0 gap).

### Q3. Which temporal component matters most?
| term | trigger prevalence | ΔAUROC vs B6_full when removed (negative = removing it helps) | mean contribution |
|---|---:|---:|---:|
| revenue (revenue_growth) | 0.141 | +0.0107 | 0.0143 |
| OCF (operating_cash_flow_growth) | 0.178 | +0.0093 | 0.0140 |
| debt (total_debt_growth) | 0.073 | +0.0010 | 0.0052 |
| cash (cash_growth) | 0.292 | -0.0039 | 0.0280 |

Largest single-term effect: **revenue** (+0.0107), which is 0.406 of the whole temporal gain — not concentrated; the gain is spread across terms.

### Q4. Does B6 depend on a few observations or one sector?
Leave-one-out over all 675 rows: observed Δ = +0.0264; range after deletion [+0.0246, +0.0269]; 0 deletion(s) reverse the sign; most influential single row = R_OBS_001989 (+0.0018).

| sector removed | n removed | ΔAUROC without it |
|---|---:|---:|
| Manufacturing | 319 | +0.0494 |
| Services | 173 | +0.0219 |
| Transportation_Utilities | 68 | +0.0273 |

### Q5. Can a strong logistic model reach B6?
Prespecified linear challenger `logistic_F2`: AUROC = 0.8190, Δ vs B6 = +0.1136 (DeLong p = 6.04e-06, Holm p = 1.21e-05, BCa [+0.0644, +0.1637]). Best regularised linear variant: 0.8361 (reported as secondary, unadjusted).

Static-only logistic (`logistic_F0`) reaches 0.8274; adding the temporal block moves it to 0.8190 (Δ = -0.0084, BCa [-0.0322, +0.0121]).

### Q6. Can strong boosting exceed B6?
`hist_gb_F2` AUROC = 0.8851, Δ vs B6 = +0.1797 (DeLong p = <1e-15 (underflow), Holm p = <1e-15 (underflow), BCa [+0.1394, +0.2239]). Secondary: random forest 0.8842, boosting on the extended family 0.8837.

### Q7. Does adding temporal features stably help the learned models?
- logistic: F0 0.8274 → F2 0.8190 (-0.0084)
- boosting: F1 (temporal only) 0.8632 → F2 0.8851 (+0.0219)
- temporal block shuffled across companies (paired design, 200 logistic and 100 boosting replicates): logistic 0.8190 → 0.8177 (median drop +0.0013, P(drop>0) = 0.605); boosting 0.8741 → 0.8617 (median drop +0.0123, P(drop>0) = 1.000)
- the *real* nonlinear temporal increment, tested head-on in §4 H3/H4: `hist_gb_F0` 0.8795 → `hist_gb_F2` 0.8851
- temporal coefficient sign consistency across outer folds:
  - revenue_growth: mean -0.0933, consistent sign negative in 0.80 of folds
  - operating_cash_flow_growth: mean -0.0454, consistent sign negative in 0.60 of folds
  - total_debt_growth: mean +0.1045, consistent sign positive in 1.00 of folds
  - cash_growth: mean -0.2656, consistent sign negative in 0.60 of folds

### Q8. Does missingness materially affect the result?
| band | n | events | B0 | B6 | Δ | Boosting-F2 |
|---|---:|---:|---:|---:|---:|---:|
| high | 225 | 157 | 0.4908 | 0.5189 | +0.0281 | 0.8623 |
| low | 225 | 21 | 0.6607 | 0.6634 | +0.0027 | 0.7682 |
| medium | 225 | 57 | 0.6153 | 0.6572 | +0.0419 | 0.7730 |

### Q9. Is B6 still transparent, simple and competitive?
B6 requires 9 packet fields, no fitting, no seed and no third-party dependency, and reaches 0.7054 against 0.8851 for the boosted model that needs nested cross-validation, imputation, scaling and a hyperparameter search. On this cohort the learned baseline is ahead.

### Q10. What does this mean for E5?
- E5 must be **prospective**: everything here is a re-reading of data E4 already published, so none of it can license a confirmatory claim.
- The comparison bar for E5 is not B0; it is a strong nested-CV tabular baseline on the same feature set, because that is what any temporal claim has to beat.
- E5 should prespecify the temporal block as a unit and report the ablation (`B6_no_temporal` is provably rank-equivalent to B0, so a null temporal effect is detectable and falsifiable).
- E5's cohort gate must be fixed before scoring: sector and missingness subgroups here are small, and only a handful clear the n≥40 / events≥10 bar.
- E5 should carry a **strong tabular baseline including a missingness-only arm**, because a model that never sees a financial value already approaches B6 here.
- The instability markers in Case F are the specific failures E5's design has to be powered against.

## 4. Hardening questions (post-hoc additions)

These come from `extension_config.json`, a second post-hoc pass written after the first report. It refines how E4-R is read; it cannot upgrade any statement to confirmatory, and `experiment_config.json` was not touched.

### H1. How much of the learned-model advantage survives removing missingness signals?
| family | arm | n | events | AUROC | 95% CI |
|---|---|---:|---:|---:|---|
| hist_gb | A_full_F2_with_indicators | 675 | 235 | 0.8851 | [0.8578, 0.9112] |
| hist_gb | B_full_F2_without_indicators | 675 | 235 | 0.8593 | [0.8272, 0.8896] |
| hist_gb | C_missingness_only | 675 | 235 | 0.8351 | [0.8008, 0.8673] |
| hist_gb | D_harmonized_availability | 413 | 63 | 0.7522 | [0.6807, 0.8194] |
| logistic | A_full_F2_with_indicators | 675 | 235 | 0.8190 | [0.7824, 0.8541] |
| logistic | B_full_F2_without_indicators | 675 | 235 | 0.6591 | [0.6120, 0.7060] |
| logistic | C_missingness_only | 675 | 235 | 0.8293 | [0.7942, 0.8622] |
| logistic | D_harmonized_availability | 413 | 63 | 0.6713 | [0.5954, 0.7422] |

| family | comparison | ΔAUROC | 95% BCa | DeLong p |
|---|---|---:|---|---:|
| hist_gb | A_minus_B_full_F2_without_indicators | -0.0258 | [-0.0403, -0.0135] | 0.000112 |
| hist_gb | A_minus_C_missingness_only | -0.0500 | [-0.0752, -0.0268] | 3.72e-05 |
| hist_gb | A_restricted_minus_D_harmonized | -0.0395 | [-0.1030, +0.0193] | 0.205 |
| logistic | A_minus_B_full_F2_without_indicators | -0.1599 | [-0.2090, -0.1102] | 1.22e-10 |
| logistic | A_minus_C_missingness_only | +0.0103 | [-0.0036, +0.0301] | 0.226 |
| logistic | A_restricted_minus_D_harmonized | +0.0189 | [-0.0748, +0.0983] | 0.663 |

- **hist_gb**: removing the missingness indicators *lowers* AUROC significantly; a material share of the learned-model advantage is attributable to reporting/missingness structure
- **logistic**: removing the missingness indicators *lowers* AUROC significantly; a material share of the learned-model advantage is attributable to reporting/missingness structure

Strict complete-case (9 of 9 fields) leaves n = 154 with 10 events and is reported as `NOT_ESTIMABLE`: 10 events cannot support an AUROC estimate; reported for completeness only.

Missingness is **not** called leakage anywhere in this study. Nothing here shows that a presence indicator carries outcome-side information; what it shows is that *whether a company reports a field at all* is a prediction-time-available characteristic that correlates with the outcome, which the open-cohort check in `leakage_audit.json` already flagged as a `REVIEW` disclosure.

### H2. What does a missingness-only model reach?
- hist_gb: AUROC 0.8351 from nine presence indicators alone, against 0.8851 for the full model (0.943× of it) and 0.7054 for B6.
- logistic: AUROC 0.8293 from nine presence indicators alone, against 0.8190 for the full model (1.013× of it) and 0.7054 for B6.

A model that never sees a single financial value reaches 0.8351, which is **+0.1297 above B6** and within 0.0500 of the best full-feature model. This is the single most important caveat in the study for anyone reading the learned-model numbers: on this cohort the availability pattern carries more usable signal than B6's five static flags and four growth terms together.

### H3. hist_gb_F0 versus hist_gb_F2: which is stronger?
`hist_gb_F0` (five static inputs) AUROC = 0.8795, PR-AUC = 0.8359. `hist_gb_F2` (static plus the four growth terms) AUROC = 0.8851, PR-AUC = 0.8387.

ΔAUROC = +0.0056 (paired DeLong p = 0.388; BCa [-0.0069, +0.0187]).

### H4. Do temporal features retain incremental value under a strong nonlinear learner?
Temporal features add little incremental value once a strong nonlinear static learner is used: the paired interval contains zero.

### H5. Does shuffling the temporal block degrade performance?
| family | replicates | original AUROC | shuffled mean | shuffle 2.5–97.5% | median drop | drop 2.5–97.5% | P(drop>0) |
|---|---:|---:|---:|---|---:|---|---:|
| hist_gb | 100 | 0.8741 | 0.8617 | [0.8504, 0.8717] | +0.0123 | [+0.0023, +0.0237] | 1.000 |
| logistic | 200 | 0.8190 | 0.8177 | [0.8064, 0.8293] | +0.0013 | [-0.0103, +0.0126] | 0.605 |

- hist_gb: paired ΔAUROC (shuffled − original) at the median-drop replicate = -0.0123 (BCa [-0.0306, +0.0052]); 0/100 shuffled replicates reach the original.
- logistic: paired ΔAUROC (shuffled − original) at the median-drop replicate = -0.0013 (BCa [-0.0251, +0.0237]); 79/200 shuffled replicates reach the original.

**Audit note on the superseded control.** In the superseded version, the first version compared a reduced-grid original arm against the full-grid headline number, which is why it printed 0.8741 against 0.8851. The arms now share one configuration and the coincidence of the outer folds with the frozen run is asserted rather than assumed. Under the shared reduced configuration the original arm reproduces at the value below; the headline 0.8851 is the full-grid fit. The difference is the inner grid, not the folds, which the fold-identity assertion above demonstrates.

| family | original arm folds identical to the frozen run |
|---|---|
| hist_gb | True |
| logistic | True |

### H6. Is sector heterogeneity real, or is the sample too small to tell?
| sector | n | events | ΔAUROC | 95% BCa | classification |
|---|---:|---:|---:|---|---|
| Agriculture | 5 | 3 | — | — | NOT_ESTIMABLE |
| Construction | 14 | 1 | — | — | NOT_ESTIMABLE |
| Manufacturing | 319 | 139 | +0.0087 | [-0.0120, +0.0308] | inconclusive |
| Mining | 33 | 16 | — | — | NOT_ESTIMABLE |
| Other_Nonfinancial | 8 | 8 | — | — | NOT_ESTIMABLE |
| Retail | 39 | 6 | — | — | NOT_ESTIMABLE |
| Services | 173 | 42 | +0.0373 | [+0.0073, +0.0840] | robust_positive |
| Transportation_Utilities | 68 | 14 | -0.0046 | [-0.0654, +0.0410] | inconclusive |
| Wholesale | 16 | 6 | — | — | NOT_ESTIMABLE |

Pooled ΔAUROC across the gated sectors (covering 560 of 675 observations, 0.830) = +0.0132.

Cochran Q = 2.2155 on 2 degrees of freedom, I² = 0.097, χ² p = 0.395; permutation p = 0.246 over 2000 relabellings.

The heterogeneity test does not reject a common effect (permutation p = 0.246), so the sector spread is compatible with sampling noise. No sector's interval supports a negative effect, so no sector can be described as one where B6 performs worse. Manufacturing, Transportation_Utilities are inconclusive: the interval spans zero, so the point estimate is not distinguishable from no effect. Services shows a robust positive effect.

### H7. Does the strong-ML-beats-B6 conclusion survive these robustness checks?
After removing every missingness signal the weaker of the two families still reaches 0.6591 against B6's 0.7054 — a gap of -0.0463. The paired boosting-vs-B6 comparison is +0.0056 for the F2 increment and the primary P3 result is unchanged. The conclusion stands, with the attribution caveat in H1 attached to it.

How much of the learned-model number is itself stable? Repeated nested cross-validation, which the primary comparisons do not integrate:

| model | repeats | mean AUROC | sd | range | per-repeat AUROC |
|---|---:|---:|---:|---:|---|
| hist_gb_F2 | 5 | 0.8800 | 0.0039 | 0.0095 | 0.8851, 0.8767, 0.8814, 0.8756, 0.8814 |
| logistic_F2 | 5 | 0.8214 | 0.0059 | 0.0145 | 0.8190, 0.8184, 0.8318, 0.8173, 0.8208 |

Refitting moves the learned AUROCs by roughly 0.0059 (sd) across 5 repeats of 5x5 nested cross-validation per model, full prespecified grid. That is an order of magnitude larger than nothing, and it is the component the DeLong and bootstrap intervals below omit.

### H8. What should E5's primary benchmark architecture be?
- A **nested-CV strong tabular baseline on the same feature set**, not B0. Beating a five-flag heuristic is not evidence of anything.
- Report the **missingness ablation alongside it**: at minimum full-features versus no-missing-indicators versus missingness-only, because a large share of the learned signal here is availability structure.
- Prespecify the **temporal block as a unit** and report the ablation; the `B6_no_temporal` rank-equivalence makes a null temporal effect a falsifiable claim.
- Fix the **sector gate and the harmonized-availability rule before scoring**, and report the heterogeneity diagnostic rather than a per-sector verdict.
- Treat **reporting completeness as a first-class baseline**, not a nuisance: any temporal or agentic claim has to beat a model that only knows what was reported.

## 5. Robustness detail

### Sector
| sector | n | events | prevalence | B0 | B6 | Δ | Boosting-F2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Agriculture | 5 | 3 | 0.600 | NOT_ESTIMABLE | — | — | — |
| Construction | 14 | 1 | 0.071 | NOT_ESTIMABLE | — | — | — |
| Manufacturing | 319 | 139 | 0.436 | 0.6435 | 0.6522 | +0.0087 | 0.8563 |
| Mining | 33 | 16 | 0.485 | NOT_ESTIMABLE | — | — | — |
| Other_Nonfinancial | 8 | 8 | 1.000 | NOT_ESTIMABLE | — | — | — |
| Retail | 39 | 6 | 0.154 | NOT_ESTIMABLE | — | — | — |
| Services | 173 | 42 | 0.243 | 0.7962 | 0.8334 | +0.0373 | 0.9280 |
| Transportation_Utilities | 68 | 14 | 0.206 | 0.6118 | 0.6071 | -0.0046 | 0.8003 |
| Wholesale | 16 | 6 | 0.375 | NOT_ESTIMABLE | — | — | — |

### Firm size
OK — split on current.total_assets (feature-side, no outcome used); 675/675 observations carry the measure

| band | n | events | B0 | B6 | Δ | Boosting-F2 |
|---|---:|---:|---:|---:|---:|---:|
| large | 225 | 30 | 0.6345 | 0.6820 | +0.0474 | 0.8503 |
| medium | 225 | 56 | 0.5967 | 0.6072 | +0.0105 | 0.8254 |
| small | 225 | 149 | 0.6042 | 0.6242 | +0.0200 | 0.8471 |

## 6. Negative controls

| scorer | mean AUROC under permuted labels | sd | 2.5% | 97.5% |
|---|---:|---:|---:|---:|
| B0 | 0.5003 | 0.0244 | 0.4565 | 0.5540 |
| B6 | 0.5001 | 0.0247 | 0.4573 | 0.5538 |
| hist_gb_F2 | 0.5008 | 0.0239 | 0.4520 | 0.5511 |
| logistic_F2 | 0.5006 | 0.0234 | 0.4570 | 0.5505 |

NC1 is a machinery check (random labels must return chance), not an equal-AUROC test.

## 7. Threshold sensitivity (`SENSITIVITY_ONLY`)

| scorer | thr | recall | specificity | precision | F1 | FNR | review load |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 0.50 | 0.545 | 0.834 | 0.637 | 0.587 | 0.455 | 0.298 |
| B6 | 0.50 | 0.498 | 0.880 | 0.688 | 0.578 | 0.502 | 0.252 |
| logistic_F2 | 0.50 | 0.609 | 0.893 | 0.753 | 0.673 | 0.391 | 0.281 |
| hist_gb_F2 | 0.50 | 0.681 | 0.907 | 0.796 | 0.734 | 0.319 | 0.298 |

Only the prespecified grid is shown; no threshold was selected and the production configuration was not touched.

## 8. Calibration (descriptive; scores remain UNCALIBRATED)

| scorer | Brier | ECE | CITL | slope | unique values | zero/one mass |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 0.2264 | 0.1699 | -0.3897 | 0.2481 | 11 | 0.479 |
| B6 | 0.2081 | 0.1279 | -0.2800 | 0.5867 | 39 | 0.274 |
| logistic_F2 | 0.1519 | 0.0305 | -0.2331 | 0.6547 | 670 | 0.006 |
| hist_gb_F2 | 0.1242 | 0.0323 | -0.0017 | 0.9687 | 663 | 0.000 |

## 9. Complexity

| scorer | family | fit seconds | dependencies | determinism |
|---|---|---:|---|---|
| B0 | deterministic heuristic | 0.00 | standard library only | exact: a pure function of the packet, no seed involved |
| B6 | deterministic heuristic | 0.00 | standard library only | exact: a pure function of the packet, no seed involved |
| hist_gb_F1 | hist_gb | 87.39 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| hist_gb_F2 | hist_gb | 102.51 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| hist_gb_F3 | hist_gb | 114.45 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| logistic_F0 | logistic | 0.55 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| logistic_F1 | logistic | 0.49 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| logistic_F2 | logistic | 0.68 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| logistic_l1_F2 | logistic_l1 | 0.92 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| logistic_l2_F2 | logistic_l2 | 1.11 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| logistic_l2_F3 | logistic_l2 | 1.28 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| random_forest_F2 | random_forest | 87.65 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |
| random_forest_F3 | random_forest | 138.83 | numpy, scipy, scikit-learn | deterministic under a fixed seed and single-threaded execution |

## 10. Limitations

- This cohort is E4-S's re-execution, not E4's exact 674 rows: E4's 270-CIK exclusion set is unpublished, so the sample is a ~94%-overlapping near-reproduction. E4-R inherits that limitation and adds no independent sample.
- 675 observations with 235 events gives a paired ΔAUROC standard error near 0.008; differences inside ±0.02 are not resolvable here.
- Only three sectors clear the n≥40 / events≥10 gate, and those three cover 0.830 of the cohort; the heterogeneity test therefore speaks about most, but not all, of the sample.
- Learned-model metrics are out-of-fold, which is the right estimator for a retrospective study but is still noisier than a single large held-out set would be.
- **Reported intervals condition on the realized out-of-fold predictions and do not fully integrate training-procedure uncertainty.** The DeLong and bootstrap intervals treat each observation's OOF score as fixed; repeated nested cross-validation shows the learned AUROCs themselves move by 0.0059 (sd) when the fold seeds change, which those intervals omit. The repeated-CV numbers are descriptive and do not enter any primary comparison.
- B0 and B6 are deterministic functions with nothing to fit; their scores are in-sample for this cohort. They carry no fitting advantage, but they also have no out-of-sample interpretation.
- Part of the learners' advantage is *reporting* itself, not just reporting values: whether a field is present at all is predictive here (the strongest missingness indicator sits 0.225 from chance), and the imputer turns that into a feature. B0 and B6 cannot see it because they simply skip absent terms. See `leakage_audit.json`.
- Calibration is descriptive only; no calibration map was fitted.

## 11. Reproduction

```bash
python research/e4r_automated_robustness/verify_e4r.py
```

Config hash `f47974607b7dd306…`, feature-set hash `09a5267044109ddd…`, seeds `{"bootstrap": 20260925, "inner_folds": 20260925, "label_permutation": 20260926, "master": 20260925, "outer_folds": 20260925, "temporal_shuffle": 20260927}`.

