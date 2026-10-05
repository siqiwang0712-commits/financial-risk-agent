# FinRisk v0.4.1 retrospective development results

Status: **RETROSPECTIVE_DEVELOPMENT / DESIGN_EXPOSED / UNCALIBRATED**

This directory publishes aggregate v0.4.1 research results only. It intentionally excludes
company identifiers, SEC accession records, row-level labels and predictions, fold
assignments, fitted models, and training or replay artifacts.

The analysis used the historically exposed E4-S verified subset: 675 observations from
675 companies, including 235 events and 440 non-events. Because the same historical
cohort informed earlier E4-R work, these metrics are development diagnostics rather than
independent validation.

## Strong tabular reference

The selected development reference used the combined financial-value and explicit
reporting-observability block (`VO`) with Histogram Gradient Boosting.

| Metric | Result |
|---|---:|
| AUROC | 0.881789 |
| PR-AUC | 0.828968 |
| Descriptive Brier score | 0.128121 |

The output is an uncalibrated ranking score, not a probability.

## Feature-block diagnostic

| Block | N | Events | Coverage | AUROC | PR-AUC | Descriptive Brier |
|---|---:|---:|---:|---:|---:|---:|
| V | 675 | 235 | 1.000000 | 0.872060 | 0.798508 | 0.133379 |
| O | 675 | 235 | 1.000000 | 0.835933 | 0.771752 | 0.145011 |
| VO | 675 | 235 | 1.000000 | 0.881789 | 0.828968 | 0.128121 |
| CC | 154 | 10 | 0.228148 | 0.676736 | 0.207292 | 0.062269 |

Reporting observability contains retrospective predictive information in this cohort. It
is not causal evidence and must not be interpreted as financial deterioration itself.

## Selective-policy diagnostic

| Arm | Coverage | Review rate | Selective error | Erroneous authorized rate | Out-of-reference authorized rate |
|---|---:|---:|---:|---:|---:|
| S0 | 1.000000 | 0.000000 | 0.189630 | 0.189630 | 0.063704 |
| S1 | 0.832593 | 0.167407 | 0.131673 | 0.109630 | 0.054815 |

This comparison is a development-only dry run. S2, S3, and S4 were not estimated.

## Boundaries

- No E5 cohort, prediction, outcome, or protocol freeze was created.
- These results do not establish calibration, predictive superiority, external validity,
  production readiness, regulatory validity, or a safety guarantee.
- B0 and B6 remain historical anchors; this result does not rewrite E1–E4-R history.

Machine-readable aggregate values are in [`summary.json`](summary.json).
