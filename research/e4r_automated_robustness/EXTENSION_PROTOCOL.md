# E4-R extension protocol — post-hoc methodological hardening

**Status: `POST_HOC_AUTOMATED_ROBUSTNESS`** (unchanged)

This file describes additions made to E4-R **after** the first `FINAL_REPORT.md` was produced.
They are a *second* post-hoc pass over the same retrospective cohort. They can make E4-R harder
to over-read; they cannot turn anything into confirmatory or prospective evidence, and they do
not change E4.

## Why a second pass at all

The first pass answered its questions but left three gaps that a reviewer would be right to
push on:

1. The learned models' advantage could be partly *reporting structure* rather than financial
   signal, and nothing in the first pass separated the two. The pipeline's imputer emits
   missing-value indicators, and whether a company reports a field at all is itself predictive.
2. The only nonlinear temporal-increment evidence compared `hist_gb_F1` (temporal only) with
   `hist_gb_F2` (combined). That says nothing about whether temporal features add value **on top
   of a strong static nonlinear learner** — `hist_gb_F0` was never run.
3. The temporal-shuffle control ran its original arm on a reduced inner grid and printed 0.8741
   while the headline model, on the full grid, is 0.8851. Two configurations were being compared
   as if they were one.

All three are fixed here.

## Boundaries honoured

- `experiment_config.json` is **byte-identical** to the version that produced the original
  results; the additions live in `extension_config.json`, which records the frozen config hash it
  was built against and aborts if that hash moves.
- No model was retuned, no observation removed, no threshold changed, and no unfavourable result
  dropped. Every arm and every sector in the original report is still reported.
- Nothing in this pass enters the P1–P3 primary family. `statistical_tests.json` is unchanged.

## What was added

### 1. Missingness confound audit (`missingness_ablation.json`)

Four arms per model family (logistic and HistGradientBoosting):

| Arm | Features | Imputation |
|---|---|---|
| A `full_F2_with_indicators` | the nine F2 fields | median + missing indicators (identical to the frozen headline runs, so arm A is not refitted) |
| B `full_F2_without_indicators` | the nine F2 fields | median only; `add_indicator=False` |
| C `missingness_only` | nine presence/absence indicators | nothing to impute |
| D `harmonized_availability` | the nine F2 fields, restricted to observations with ≥ 7 of 9 present | median + indicators, refitted within the subset |

`A − B` is the part of the advantage carried by missingness structure. `C` is what a model that
never sees a financial value can do. `A|subset − D` asks whether restricting to data-complete
companies changes the learned model.

Strict complete-case (9 of 9 fields) leaves 154 observations and 10 events and is reported as
`NOT_ESTIMABLE` rather than estimated.

**Missingness is never called leakage here.** The claim that would have to be demonstrated for
that — a presence indicator carrying outcome-side information — is not made and is not supported:
the labels are built from future filings, and the audit's timestamp checks pass. What is
demonstrated is that *availability structure is a legitimate prediction-time feature with real
predictive content*, which is a different and weaker statement.

### 2. Boosting temporal increment (`boosting_temporal_increment.json`)

`hist_gb_F0` (five static B0 inputs) is run under the full prespecified grid, then compared with
`hist_gb_F2` using a paired DeLong test and a 20 000-replicate paired BCa bootstrap. This is the
comparison that answers whether temporal features retain incremental value under a strong
*nonlinear* learner.

### 3. Temporal shuffle control, rebuilt (inside `negative_controls.json`)

- one shared configuration for both arms (the reduced inner grid, stated);
- identical outer folds, identical inner folds, identical preprocessing, identical seed;
- only the temporal block is permuted across companies;
- 200 replicates for logistic, 100 for boosting;
- the original arm's folds are **asserted** to equal the frozen run's folds, and that assertion is
  recorded in the artifact;
- reported: original AUROC, the shuffled distribution, mean and median drop, the across-replicate
  2.5–97.5% interval, `P(drop > 0)`, and a paired cluster-bootstrap interval at the median
  replicate. Two different sources of variability, both stated.

The superseded 0.8741 is explained rather than deleted: it was the reduced-grid original arm, not
a different data set, and the fold-identity assertion demonstrates it.

### 4. Sector heterogeneity (`sector_heterogeneity.json`)

Per gated sector: ΔAUROC(B6 − B0) with a sector-internal bootstrap interval, classified as
`robust_positive` (interval above zero), `possible_heterogeneity` (interval below zero) or
`inconclusive` (interval spans zero). Heterogeneity is tested with Cochran's Q
(inverse-variance-weighted) and, because three sectors make the χ² approximation unreliable, with a
2 000-replicate permutation null that holds the weights fixed at their observed values — an
approximation that is stated rather than hidden.

### 5. Model stability (`model_stability.json`)

Five repeats of 5×5 nested cross-validation per learned challenger, full grid, seeds
`20260925 + 101·repeat`. Descriptive only; it quantifies the training-procedure variance that the
primary DeLong and bootstrap intervals condition away.

## Reading rules for the additions

- The additions use the same pre-registered case vocabulary as `INTERPRETATION_POLICY.md`.
  Case F's sector marker was **tightened** (see the policy file): a sector now only marks
  instability when its interval supports a negative effect, or when the interval spans zero and
  the point estimate is negative. Tightening can only make Case F harder to fire.
- No statement in this pass is a confirmatory test.
- Every number is produced by `run_e4r.py --extensions` (or a normal run) and is verifiable with
  `verify_e4r.py`.
