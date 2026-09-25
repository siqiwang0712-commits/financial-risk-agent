# E4-R — Automated Robustness & Competitive Baseline Study

**Status: `POST_HOC_AUTOMATED_ROBUSTNESS`**

E4-R is a **retrospective** study. It re-reads data E4 has already published. It is **not**
`ESTABLISHED_E4`, **not** `CONFIRMATORY`, **not** `PROSPECTIVE` and **not** an `E5_RESULT`.

- it does **not** modify E4 — no frozen artifact, threshold, label or cohort is touched;
- it does **not** create confirmatory evidence;
- it does **not** replace E5;
- it evaluates robustness and competitive baselines only, so that E5 can be designed.

> **Question.** On E4's published data, how robust is the B6 temporal signal, and can simple
> or strong tabular machine-learning methods — given the same information — explain,
> reproduce or exceed B6?

---

## Run it

```bash
# freeze the prespecification (only writes if absent; never overwritten afterwards)
python research/e4r_automated_robustness/e4r_config.py

# the study (about 25 minutes: 11 nested-CV runs plus 20,000-replicate bootstraps)
python research/e4r_automated_robustness/run_e4r.py

# verify every hash, the frozen config, the outputs and the headline statistics
python research/e4r_automated_robustness/verify_e4r.py
```

Extra dependencies (not shipped by the product runtime, installed as the `research` extra):
`numpy`, `scipy`, `scikit-learn`, `matplotlib`.

---

## Source

Everything comes from `research/e4_statistical_audit/replication/` — the E4-S replication
packet. Before any analysis the pipeline:

1. verifies the SHA-256 of every file in the replication `manifest.json`;
2. verifies the frozen E4 artifact manifest (proving E4-R did not mutate E4);
3. runs the existing E4-S verifier (`verify_audit.py --quick`, output to a scratch path so
   the committed E4-S result is untouched);
4. reconstructs B0 and B6 from the packet's own metrics with the **frozen** scoring
   functions and checks them against the published scores.

Integrity failure stops the study. Nothing is auto-repaired.

**Cohort:** outcome rows with `label_status == VERIFIED` — **n = 675**, **235 events**
(34.8%), one observation per company.

---

## What is prespecified, and when

`experiment_config.json` and `feature_sets.json` were written **before** the first formal
run and are never overwritten. The pipeline aborts if their hashes move. The rules for
reading the results (`INTERPRETATION_POLICY.md`) were also fixed first, and `e4r_report.py`
applies them mechanically.

| Prespecified | Value |
|---|---|
| outer folds | `StratifiedGroupKFold(5)`, grouped on company, stratified on label, seed 20260925 |
| inner folds | `StratifiedGroupKFold(5)` on the outer training portion only |
| preprocessing | `SimpleImputer(median, add_indicator=True) → StandardScaler`, fitted inside the fold |
| primary family | P1 `B6 vs B0`, P2 `Logistic-F2 vs B6`, P3 `Boosting-F2 vs B6` — Holm-corrected |
| statistics | paired DeLong + 20,000-replicate paired BCa cluster bootstrap |
| subgroup gate | sector reported only at `n ≥ 40` **and** `events ≥ 10`, else `NOT_ESTIMABLE` |
| threshold grid | `{0.30, 0.40, 0.50, 0.60, 0.70}`, `SENSITIVITY_ONLY` |

Random forest is deliberately secondary. Gradient boosting uses scikit-learn's
`HistGradientBoostingClassifier`: XGBoost would add a second heavy dependency to a
repository that ships no numeric stack at all, which is exactly the substitution the
protocol allows.

---

## Files

| File | Contents |
|---|---|
| `README.md`, `STUDY_PROTOCOL.md`, `INTERPRETATION_POLICY.md` | protocol and pre-registered decision rules |
| `experiment_config.json`, `feature_sets.json` | frozen prespecification |
| `leakage_audit.json` | automated leakage and structural-disclosure audit |
| `oof_predictions.csv` / `.json` | every observation × model, with B0/B6 alongside |
| `model_results.json` | out-of-fold AUROC / PR-AUC per scorer |
| `temporal_ablation.json` | B6 rebuilt with each temporal term removed |
| `temporal_contribution_summary.json` | per-term trigger prevalence and contribution |
| `temporal_incremental_test.json` | `Y ~ F0` vs `Y ~ F0 + temporal`, coefficient stability |
| `subgroup_results.json` | sector, firm size, missingness |
| `influence_analysis.json` | leave-one-out and leave-sector-out |
| `negative_controls.json` | label permutation, and the paired temporal-alignment control |
| `calibration_diagnostics.json` | descriptive; scores stay `UNCALIBRATED` |
| `threshold_robustness.json` | `SENSITIVITY_ONLY` sweep |
| `statistical_tests.json` | DeLong, BCa, Holm |
| `complexity_comparison.json` | fit time, dependencies, determinism |
| `extension_config.json`, `EXTENSION_PROTOCOL.md` | the post-hoc hardening prespecification and its rationale |
| `missingness_ablation.json` | four arms per family: full, no indicators, missingness-only, harmonized subset |
| `boosting_temporal_increment.json` | `hist_gb_F0` vs `hist_gb_F2` |
| `sector_heterogeneity.json` | per-sector ΔAUROC intervals, Cochran Q, permutation test |
| `model_stability.json` | repeated nested CV: the training-procedure variance the main intervals omit |
| `FINAL_REPORT.md` | generated from the artifacts above |
| `manifest.json`, `verify_e4r.py` | hashes, environment, one-command verification |
| `figures/` | 7 SVGs rendered from the artifacts |

Code: `e4r_data` (integrity + cohort), `e4r_stats` (inference, reusing `e4s_stats`),
`e4r_ablation`, `e4r_models` (nested CV), `e4r_leakage`, `e4r_analysis`, `e4r_figures`,
`e4r_report`, `run_e4r`, `e4r_config`.

---

## Reading the result

Start with `FINAL_REPORT.md`. Three things about it:

- it is **generated** from the JSON artifacts, so the prose cannot drift from the numbers;
- the interpretation cases (A–F) come from `INTERPRETATION_POLICY.md`, applied as code;
- anything the data cannot support says `NOT_ESTIMABLE` rather than being quietly dropped.

Two structural facts are worth knowing before reading any number:

1. **`B6_no_temporal` is `0.75 × B0`.** Since B0 lies in [0, 1] that is a strictly
   increasing map of B0, so `AUROC(B6_no_temporal)` equals `AUROC(B0)` *exactly*. The
   temporal block is the only component of B6 that can reorder observations. This is a
   structural decomposition of a deterministic formula, not a causal finding.
2. **The endpoint is a transition rule.** Four of the five conditions behind
   `financial_deterioration_12m` compare the FY2025 fact with the FY2024 fact and two are
   gated on the FY2024 value being positive. FY2024 facts are visible before the cutoff, so
   this is *not* leakage — but pre-cutoff magnitudes are strongly informative about the
   label. The leakage audit records this as a `REVIEW` disclosure with the univariate
   signal screen that shows it.

---

## Post-hoc hardening pass

A second post-hoc pass, described in `EXTENSION_PROTOCOL.md` and driven by
`extension_config.json` (which cannot move `experiment_config.json`). It closes three gaps a
reviewer would be right to push on:

1. **Missingness confound audit.** Four arms per family — full F2 with indicators, full F2
   without indicators, missingness-indicators-only, and a harmonized-availability subset
   (≥ 7 of 9 fields). This separates financial-value signal from reporting-structure signal.
   Missingness is **not** called leakage: the claim that would require is not made and is not
   supported.
2. **The real nonlinear temporal increment.** `hist_gb_F0` (static only) versus `hist_gb_F2`,
   with a paired DeLong test and a 20 000-replicate BCa interval. The old
   `hist_gb_F1 → hist_gb_F2` comparison could not answer whether temporal features add value
   *on top of a strong static nonlinear learner*, because `hist_gb_F0` did not exist.
3. **A genuinely paired temporal-shuffle control.** One shared configuration for both arms,
   the original arm's folds asserted equal to the frozen run's, 200 (logistic) / 100
   (boosting) replicates, and both sources of variability reported. The superseded 0.8741
   against the headline 0.8851 is explained rather than deleted: it was the reduced-grid
   original arm.

Plus a **sector heterogeneity** section (per-sector intervals, Cochran Q, a permutation
null) so a 68-observation sector is not read as a sector failure, and **repeated nested CV**
so the training-procedure variance the main intervals omit is at least measured.

`INTERPRETATION_POLICY.md` gained a "phrasing clarifications" section recording three
changes: the temporal block must be described structurally rather than causally; Case F's
sector marker now requires interval support (strictly harder to fire); and the OOF
uncertainty limitation is stated explicitly. No threshold or case membership changed.
