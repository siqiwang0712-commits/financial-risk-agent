# Results

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

The 30-company experiment is NOT RUN because SEC acquisition was blocked. No result has been imputed or fabricated.
