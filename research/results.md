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

| Baseline | Decisions | Accuracy | Balanced accuracy | Risk F1 | AUROC | AUPRC | Brier | ECE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LLM Only (mock) | 3/3 | .667 | .500 | .000 | .500 | 1.000 | .333 | .333 |
| Ratios Only | 3/3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | .104 | .250 |
| Rule Engine | 3/3 | .667 | .750 | .667 | 1.000 | 1.000 | .235 | .371 |
| Traditional Models | 3/3 | .333 | .500 | .500 | .500 | 1.000 | .250 | .167 |
| Full Hybrid | 2/3 | .500 | .500 | .000 | 1.000 | 1.000 | .193 | .407 |

Full Hybrid abstained on Apple, correctly classified Microsoft and missed Intel. Its contradiction F1 is .667. Accuracy intervals span [0,1] except Ratios Only [1,1]; at n=3 even that interval is not evidence of generalization. AUPRC is especially unstable with one positive example.

## RQ status

- RQ1: not answered. Mock claims were verified, but no real LLM baseline ran.
- RQ2: engineering evidence only; one true positive and one Apple false positive yield F1 .667.
- RQ3: not supported in this pilot. Ratios Only outperformed Full Hybrid.
- RQ4: supported as a diagnostic: predictions are unstable when modules or trends are removed.

## Robustness checks

Multiplying every monetary input by 1,000 left all scores and predictions unchanged, confirming scale invariance for the exercised pipeline. Deterministic 10% and 30% field deletion reduced evidence confidence as designed. Intel remained a false negative; at 30% missingness its score fell from 42.7 to 36.3 and confidence from .65 to .51. Apple continued to abstain. Raw results are in `robustness.csv/json`.

The statement above describes the historical `public_v1` narrative pilot. The separate v0.3.1 numeric experiment is now run on the 30-company corpus as reported at the top of this file; narrative/LLM B3–B5/B8 remain not run. No missing result has been imputed or fabricated.
