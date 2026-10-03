# Reporting observability diagnostic

Status: **RETROSPECTIVE_DEVELOPMENT_DIAGNOSTIC**

This cohort is historically exposed, the verified-label subset is selective, and all metrics are development diagnostics. This is not E5 or independent validation.

| Block | N | Coverage | AUROC | PR-AUC | Descriptive Brier (uncalibrated) |
|---|---:|---:|---:|---:|---:|
| V | 675 | 1.000 | 0.872 | 0.799 | 0.133 |
| O | 675 | 1.000 | 0.836 | 0.772 | 0.145 |
| VO | 675 | 1.000 | 0.882 | 0.829 | 0.128 |
| CC | 154 | 0.228 | 0.677 | 0.207 | 0.062 |

Development-only VO minus V AUROC: `+0.010`; PR-AUC: `+0.030`.

Reporting observability may carry retrospective predictive information in this historical cohort. It is not causal evidence and is not financial severity. Production FinRisk continues to keep reporting observability separate from financial values.

Canonical source: [`artifacts/observability_diagnostic.json`](artifacts/observability_diagnostic.json).
