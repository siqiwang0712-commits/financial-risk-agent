# Results

## v0.3.1 empirical numeric run

The frozen 30-company × 3-year SEC Financial Statement Data Set corpus contains 90 filing-level observations and passes point-in-time integrity with zero company overlap and zero detected future leakage. E3's separate label-only outcome pool and corrected calendar-12-month endpoint produced 42 verified labels (34 negative, 8 positive), 6 review-required cases, 17 true no-eligible-outcome records and 25 right-censored records.

The E3 held-out evaluation contains six labelled observations from five companies and one positive endpoint. Results were: B0 Ratios AUROC 0.100, PR-AUC 0.200, F1 0.000; B1 Logistic Regression AUROC 0.200, PR-AUC 0.200, F1 0.000; B2 Rules AUROC 0.100, PR-AUC 0.200, F1 0.000; B6 Numeric Temporal AUROC 0.100, PR-AUC 0.200, F1 0.000. All four baselines had a false-negative rate of 1.0. B6 minus B0 balanced-accuracy delta was 0.000; 691/1,000 cluster replicates retained both classes and 309 were invalid, so the interval is `CI_NOT_ESTIMABLE`, not `[0,0]`.

These results do not establish predictive superiority. Statistical power is inadequate, the secondary label is deterministic rather than human-adjudicated hard distress, and the extraction check is a machine presentation-to-number reconciliation rather than independent human gold. It reconciled 1,165 comparable fields and agreed on 1,164 (99.914% machine agreement); the one Ford 2023 mismatch is a documented `ProfitLoss` versus `NetIncomeLoss` construct ambiguity requiring manual adjudication. Raw E1/E2/E3 predictions, manifests and forensic reports are retained for audit.

## Research questions

- **RQ1:** Does hybrid reasoning reduce unsupported claims relative to semantic-only analysis?
- **RQ2:** Does numeric-plus-narrative consistency detection improve contradiction F1 over narrative-only extraction?
- **RQ3:** Does Full Hybrid improve company-level risk classification over ratios, rules and traditional models under company-disjoint evaluation?
- **RQ4:** How sensitive are predictions to narrative, rules, models, temporal trends and missing inputs?

## Executed pilot

The evaluated set is `n=3`, not the planned 30-company confirmatory corpus. Raw predictions, decompositions, confusion matrices and ablations are committed in `research/results/public_v1`.

### Reproducibility caveat (2026-09-14)

`research/results/public_v1` is **frozen at the v0.3.0 code and is no longer byte-reproducible from the current code**. Two Intel figures moved when the audit remediation landed:

| Row | Frozen `public_v1` | Current code | Cause |
|---|---:|---:|---|
| `intc-2024` / `full_hybrid` risk probability | 0.427 | 0.391 | the model-mapping operator table was unified and the uncaught `StopIteration` path removed, which changed which model signals Intel triggers |
| `intc-2024` / `without_trends` risk probability | 0.340 | 0.283 | same |

Every other value is unchanged. The frozen files are kept as they are because they are the pilot口径 cited below and in `research/error_analysis.md`, and because CI verifies they are never rewritten. Regenerating them is a separate decision that would require re-issuing the pilot; the same drift is visible in `examples/intel_2024_sample_report.txt`, which *is* regenerable and has been brought back in step with the code (39.1/100, Low).

Re-running `scripts/run_public_benchmark.py` today would therefore produce two different Intel numbers, not a corrupted run.

| Baseline | Decisions | Accuracy | Balanced accuracy | Risk F1 | AUROC | AUPRC | Brier | ECE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LLM Only (mock) | 3/3 | .667 | .500 | .000 | .500 | 1.000 | .333 | .333 |
| Ratios Only | 3/3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | .104 | .250 |
| Rule Engine | 3/3 | .667 | .750 | .667 | 1.000 | 1.000 | .235 | .371 |
| Traditional Models | 3/3 | .333 | .500 | .500 | .500 | 1.000 | .250 | .167 |
| Full Hybrid | 2/3 | .500 | .500 | .000 | 1.000 | 1.000 | .193 | .407 |

Full Hybrid abstained on Apple, correctly classified Microsoft and missed Intel. Its contradiction F1 is .667 in the frozen v0.3.0 `public_v1` run; the separate v0.3.1 integrity replay, which re-scores claim-conditioned evidence on the v0.3.1 evidence set, raises it to 1.000 (see `research/results/v0.3.1/decision_integrity_replay.json`). Both figures are n=3 diagnostics with single-reviewer labels and neither is evidence of generalization. Accuracy intervals span [0,1] except Ratios Only [1,1]; at n=3 even that interval is not evidence of generalization. AUPRC is especially unstable with one positive example.

The `Full Hybrid` row is scored with the expert-weighted aggregate over risk dimensions (`scoring.aggregate`). The Agent decision path uses hierarchical escalation instead, so this row does **not** describe the strategy the product decides with. `decision_integrity_replay.json` compares both on the v0.3.1 evidence, but no experiment reports predictive metrics for hierarchical escalation against the labelled endpoint.

## Artifacts

- [Machine-readable summary](results/public_v1/summary.json)
- [Raw predictions](results/public_v1/predictions.csv)
- [Per-company score decomposition](results/public_v1/score_decomposition.csv)
- [Confusion matrices](results/public_v1/confusion_matrices.csv)
- [Ablations](results/public_v1/ablations.csv)
- [Robustness checks](results/public_v1/robustness.csv)
- [Error analysis](error_analysis.md)

## RQ status

- RQ1: not answered. Mock claims were verified, but no real LLM baseline ran.
- RQ2: engineering evidence only; one true positive and one Apple false positive yield F1 .667.
- RQ3: not supported in this pilot. Ratios Only outperformed Full Hybrid.
- RQ4: supported as a diagnostic: predictions are unstable when modules or trends are removed.

## Robustness checks

Multiplying every monetary input by 1,000 left all scores and predictions unchanged, confirming scale invariance for the exercised pipeline. Deterministic 10% and 30% field deletion reduced evidence confidence as designed. Intel remained a false negative; at 30% missingness its score fell from 42.7 to 36.3 and confidence from .65 to .51. Apple continued to abstain. Raw results are in `robustness.csv/json`.

The statement above describes the historical `public_v1` narrative pilot. The separate v0.3.1 numeric experiment is now run on the 30-company corpus as reported at the top of this file; narrative/LLM B3–B5/B8 remain not run. No missing result has been imputed or fabricated.
