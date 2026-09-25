# E4-R — Automated Robustness & Competitive Baseline Study

**Status: `POST_HOC_AUTOMATED_ROBUSTNESS`** — git `f4f002f492d9`, Python 3.13.14.

E4-R is a **retrospective (POST_HOC)** study run on E4's published replication data. It is **not** `ESTABLISHED_E4`, **not** `CONFIRMATORY`, **not** `PROSPECTIVE` and **not** an `E5_RESULT`. It does not modify E4, does not create confirmatory evidence, and does not replace E5. It exists to make E5 designable.

- cohort: **n = 675**, events = **235**, prevalence = **0.348**
- leakage audit: **REVIEW** (16/18 checks pass; disclosed as REVIEW, not leakage: endpoint_anchored_on_pre_cutoff_levels, missingness_indicators_carry_signal)
- primary multiplicity control: Holm across P1–P3
- bootstrap replicates: 20000

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
  - sector Transportation_Utilities: ΔAUROC(B6−B0) = -0.0046 ≤ 0

## 3. The ten questions

### Q1. Does B6 > B0 still hold under re-check?
Yes. B0 AUROC = 0.6791, B6 AUROC = 0.7054, Δ = +0.0264 (BCa 95% [+0.0109, +0.0434], Holm p = 0.00144). This is a replication sanity check on E4's own data, not a new confirmation.

### Q2. Is the temporal signal really the main incremental source?
Removing the whole temporal block gives AUROC = 0.6791. Because `B6_no_temporal` is `0.75 × B0`, a strictly increasing map of B0, that value equals AUROC(B0) (0.6791) **exactly** — the check is structural, not empirical. The temporal block therefore accounts for the entire B6 − B0 separation (+0.0264); this meets the DESTROYED criterion (≥80% of the gain).

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
- NC2 (temporal block shuffled across companies, 10 replicates): logistic 0.8190 → 0.8171 (drop +0.0019); boosting 0.8741 → 0.8623 (drop +0.0118)
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
- The instability markers in Case F are the specific failures E5's design has to be powered against.

## 4. Robustness detail

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

## 5. Negative controls

| scorer | mean AUROC under permuted labels | sd | 2.5% | 97.5% |
|---|---:|---:|---:|---:|
| B0 | 0.5003 | 0.0244 | 0.4565 | 0.5540 |
| B6 | 0.5001 | 0.0247 | 0.4573 | 0.5538 |
| hist_gb_F2 | 0.5008 | 0.0239 | 0.4520 | 0.5511 |
| logistic_F2 | 0.5006 | 0.0234 | 0.4570 | 0.5505 |

NC1 is a machinery check (random labels must return chance), not an equal-AUROC test.

## 6. Threshold sensitivity (`SENSITIVITY_ONLY`)

| scorer | thr | recall | specificity | precision | F1 | FNR | review load |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 0.50 | 0.545 | 0.834 | 0.637 | 0.587 | 0.455 | 0.298 |
| B6 | 0.50 | 0.498 | 0.880 | 0.688 | 0.578 | 0.502 | 0.252 |
| logistic_F2 | 0.50 | 0.609 | 0.893 | 0.753 | 0.673 | 0.391 | 0.281 |
| hist_gb_F2 | 0.50 | 0.681 | 0.907 | 0.796 | 0.734 | 0.319 | 0.298 |

Only the prespecified grid is shown; no threshold was selected and the production configuration was not touched.

## 7. Calibration (descriptive; scores remain UNCALIBRATED)

| scorer | Brier | ECE | CITL | slope | unique values | zero/one mass |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 0.2264 | 0.1699 | -0.3897 | 0.2481 | 11 | 0.479 |
| B6 | 0.2081 | 0.1279 | -0.2800 | 0.5867 | 39 | 0.274 |
| logistic_F2 | 0.1519 | 0.0305 | -0.2331 | 0.6547 | 670 | 0.006 |
| hist_gb_F2 | 0.1242 | 0.0323 | -0.0017 | 0.9687 | 663 | 0.000 |

## 8. Complexity

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

## 9. Limitations

- This cohort is E4-S's re-execution, not E4's exact 674 rows: E4's 270-CIK exclusion set is unpublished, so the sample is a ~94%-overlapping near-reproduction. E4-R inherits that limitation and adds no independent sample.
- 675 observations with 235 events gives a paired ΔAUROC standard error near 0.008; differences inside ±0.02 are not resolvable here.
- Only three sectors clear the n≥40 / events≥10 gate, so sector conclusions are thin.
- Learned-model metrics are out-of-fold, which is the right estimator for a retrospective study but is still noisier than a single large held-out set would be.
- B0 and B6 are deterministic functions with nothing to fit; their scores are in-sample for this cohort. They carry no fitting advantage, but they also have no out-of-sample interpretation.
- Part of the learners' advantage is *reporting* itself, not just reporting values: whether a field is present at all is predictive here (the strongest missingness indicator sits 0.225 from chance), and the imputer turns that into a feature. B0 and B6 cannot see it because they simply skip absent terms. See `leakage_audit.json`.
- Calibration is descriptive only; no calibration map was fitted.

## 10. Reproduction

```bash
python research/e4r_automated_robustness/verify_e4r.py
```

Config hash `f47974607b7dd306…`, feature-set hash `09a5267044109ddd…`, seeds `{"bootstrap": 20260925, "inner_folds": 20260925, "label_permutation": 20260926, "master": 20260925, "outer_folds": 20260925, "temporal_shuffle": 20260927}`.

