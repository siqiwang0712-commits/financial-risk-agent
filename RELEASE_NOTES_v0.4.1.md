# FinRisk v0.4.1 — Research Readiness & Strong Reference

**Version:** `0.4.1` · **Status:** release-review candidate; prospective E5 and external
validation remain pending.

## Why v0.4.1 exists

v0.4.1 moves the v0.4 Assurance architecture from engineering-only readiness toward a
measurable prospective-study foundation. It adds a reproducible historical strong tabular
reference, explicit reporting-observability diagnostics, a label-independent empirical
development reference, selective-evaluation tooling, and stage-aware E5 preflight.
Financial scoring and the historical fitted reference are unchanged. Final review hardens
pre-parse upload admission, numeric contradiction provenance, malformed Assurance verification
and missing-authorization display; previously unsupported paths can now require review or
abstention. Frozen E1–E4-R evidence is unchanged.

## StrongTabularReference-v1

- Development source: frozen E4-S replication packet; 675 verified companies/observations,
  235 events and 440 non-events.
- Exposure: `DESIGN_EXPOSED_HISTORICAL_DEVELOPMENT`; E4-R used the same labelled rows and
  informed the candidate families/grids.
- Future isolation: all 2,000 companies in the E4-S source cohort are mandatory future E5
  exclusions.
- Endpoint: `financial_deterioration_12m` /
  `deterministic_forward_outcome_rule_v1`, 12-month horizon. Eventual E5 endpoint
  compatibility remains a protocol-freeze check.
- Mechanical selection: `VO` + Histogram Gradient Boosting
  (`histogram_gradient_boosting`) with learning rate `0.05`,
  maximum leaf nodes `7`, minimum leaf size `20`, L2 regularization `1.0`, `log_loss`, and
  early stopping disabled.
- Retrospective-development OOF metrics: AUROC `0.8817891682785299`, PR-AUC
  `0.8289679250748645`, and descriptive uncalibrated Brier `0.12812086027177813`.
- Fitted artifact identity:
  `3e1ebd825f1699bcc88e52a531bf9199aad3e93a671cfe28640f15dd33759a26`.
- Fitted-artifact replay runtime: Python 3.12.14, NumPy 2.5.3, scikit-learn 1.9.1.
  Trusted loading verifies model/preprocessor hashes before deserialization; the fixed
  replay sample verifies only on that pinned numeric stack. The product package remains
  tested on Python 3.11 and 3.12; an incompatible research replay fails closed.

These metrics are `RETROSPECTIVE_DEVELOPMENT_SELECTION_METRICS`, not independent or
prospective performance estimates. The output is an `UNCALIBRATED_RANKING_SCORE`, not a
probability, and it has no final-decision authority.

## Reporting observability

| Block | N | Events | Coverage | AUROC | PR-AUC | Descriptive Brier (uncalibrated) |
|---|---:|---:|---:|---:|---:|---:|
| V | 675 | 235 | 1.000000 | 0.872060 | 0.798508 | 0.133379 |
| O | 675 | 235 | 1.000000 | 0.835933 | 0.771752 | 0.145011 |
| VO | 675 | 235 | 1.000000 | 0.881789 | 0.828968 | 0.128121 |
| CC | 154 | 10 | 0.228148 | 0.676736 | 0.207292 | 0.062269 |

VO − V is +0.009729 AUROC and +0.030459 PR-AUC in this development exercise. Reporting
observability carries retrospective predictive information in this historical cohort. It
is not a causal finding and does not become production financial severity. CC has only 10
events and 22.8% coverage; it is a small-subset sensitivity result, not a directly
comparable full-cohort estimate.

## Empirical development reference

The checked-in profile is `EMPIRICAL_DEVELOPMENT_REFERENCE_ONLY`. It is built from the
2,000 source-cohort prediction-time rows without labels and keeps financial values and
reporting observability separate. It is neither an E5-frozen, external, regulatory, nor
production reference and is not silently installed into the production runtime.
Its canonical reference identity is
`ff8693a91b1c9f4e15e12a5426531cce5e5ca5cc6742a5f4379b3413d08da86e`.

## Selective evaluation

The hash-bound development-only S1 rule was specified before the final comparison.

| Arm | Coverage | Review rate | Selective error | Erroneous authorized rate | Out-of-reference authorized rate |
|---|---:|---:|---:|---:|---:|
| S0 | 1.000000 | 0.000000 | 0.189630 | 0.189630 | 0.063704 |
| S1 | 0.832593 | 0.167407 | 0.131673 | 0.109630 | 0.054815 |

Here, “out-of-reference” has the narrow registered rule recorded in the artifact: at
least one observed financial-value feature lies outside its all-2,000-source-row q01–q99
range. Missing values are described separately by the observability profile. This is not
a general distribution-validity or production-safety claim.

This is a `RETROSPECTIVE_DEVELOPMENT_DRY_RUN`, not a confirmatory comparison. Unsupported
authorized-decision rate is `NOT_ESTIMABLE` because no separate support-label target exists.
S2/S3/S4 are `NOT_ESTIMABLE_IN_V0.4.1`: a fair run would require frozen Agent identities
and full filing-text packets not present in the tabular replication packet.

## E5 readiness

Completed for v0.4.1: approved historical development data, fitted/replayable historical
S0, observability diagnostics, empirical development reference, explicit uncalibrated
status, runtime policy/certificate release identities, and stage-aware preflight.

Still blocked: final primary estimands/multiplicity/effect thresholds, E5 reference and
arm identities, future time window/cohort, the unpublished 270-company exclusion,
prediction environment/isolation, prediction freeze, and outcome unlock. E5 remains
`BLOCKED / DRAFT_NOT_FROZEN`; no E5 cohort, prediction, outcome, or final freeze hash exists.

## Verification

Lightweight checked-in artifact gate:

```bash
python scripts/verify_v041.py
```

Explicit expensive rebuild:

```bash
python -m research.strong_tabular_reference.run_development
```

The [final release audit](docs/RELEASE_AUDIT_v0.4.1.md) is the single current record of
commands, actual test totals/coverage, warnings, clean wheel checks, and remote image
verification. Local backend/frontend/research/package checks pass; this host's Docker
Desktop engine fails to start, so the local gate does **not** claim an aggregate pass.
Container evidence must identify the final branch HEAD and its `publish=false` workflow.

No nested-CV rebuild runs during normal CI.

## Limitations

- development data are `DESIGN_EXPOSED` and verification/outcome availability is selective;
- development CV is not independent validation or an unbiased future performance estimate;
- scores are `UNCALIBRATED` and must not be interpreted as probabilities;
- E5 has not run and the 270-company historical exclusion remains unavailable;
- no external, production, regulatory, predictive-superiority, or safety guarantee is made.
