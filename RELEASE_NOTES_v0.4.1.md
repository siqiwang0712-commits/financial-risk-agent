# FinRisk v0.4.1 — Research Readiness & Strong Reference

**Version:** `0.4.1` · **Released:** 2026-10-05

Research-prototype software release. Prospective E5 and external validation remain
pending; scores and the Assurance policy remain `UNCALIBRATED`.

## Why v0.4.1 exists

v0.4 introduced a separate authorization layer: prediction components propose a decision;
only a valid, policy-bound AssuranceResult can authorize `final_decision` and a Decision
Certificate. v0.4.1 completes research-readiness and release hardening around that boundary,
without claiming new prospective predictive evidence.

The release adds a reproducible historical strong tabular reference, approved historical
development manifest, V/O/VO/CC observability diagnostics, label-independent empirical
development reference, selective-evaluation machinery and stage-aware E5 preflight.
It also hardens pre-parse upload admission, numeric contradiction provenance, malformed
Assurance rejection, certificate-bound authorization display and mounted-secret handling.
Previously unsupported paths can now require review or abstention. Financial scoring,
fitted historical reference artifacts and frozen E1–E4-R evidence were not changed by
release hardening or documentation closeout.

## StrongTabularReference-v1 and approved development data

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
probability, and it has no final-decision authority. The approved source is explicitly
`DESIGN_EXPOSED`; it cannot serve again as fresh validation. See the
[canonical results](research/strong_tabular_reference/artifacts/canonical_results.json)
and [reference artifact contract](research/strong_tabular_reference/README.md).

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

Original frozen E4 contains 674 verified outcomes and 235 events; E4-S / this historical
development reference contains 675 observations, 235 events and 440 non-events. These
are distinct historical objects. B0/B6 remain historical anchors, not the strongest
competitive reference. E4-R's finding that learned tabular baselines outperform B6 remains
visible and unchanged. See the [research overview](research/EXPERIMENT_OVERVIEW.md).

## Final engineering verification

Final runtime source: `00fc338f73be0529a4adc6a1705d518af7bf8030`.
The final documentation commit changes no runtime or research artifact. Its SHA is
recorded in Git history; the following evidence belongs to the tested runtime source,
not to a newly built image from the documentation commit.

| Gate | Verified evidence |
|---|---|
| Normal CI | [37302574534](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/37302574534): all four jobs passed |
| Python 3.11 / 3.12 on Linux | Each: 781 passed, 0 skipped, 84 warnings, 92.08% coverage; required threshold remains 90% |
| Ruff and backend dependency audits | Passed; `pip check` and locked `pip-audit` passed |
| Frontend | 34 tests, lint, TypeScript and production build passed; production dependency audit reported 0 vulnerabilities |
| Package / clean installs | Local wheel and sdist build passed; clean installed-wheel API/pipeline/Assurance/certificate smoke passed outside the checkout on both Python versions |
| Research gates | StrongTabularReference artifact/replay, release runtime identities and E5 preflight passed; E4 public integrity passed, E4-S 44/44, E4-R 136/136 |
| Container dry-run | [37302629899](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/37302629899): `workflow_dispatch`, `version=v0.4.1`, `publish=false` |
| Real-stack verification | Both build jobs, development-overlay verification and release Compose verification passed using exact candidate digests |
| PostgreSQL / API | Migrations, readiness/liveness, bootstrap/authentication, v0.4.1 serialization, certificate generation/replay and restart persistence passed |
| Timeout / retry | Controlled 504 followed by explicit retry returning 504 passed |
| Container security | Both vulnerability and secret scans passed; candidate identity was verified and both Trivy JSON reports were retained and inspected |
| Publication | Skipped in the audited dry-run; no release-tag publication is claimed by that evidence |

Local Windows suites each recorded 763 passed, 18 environment-gated skips and 91.09%
coverage. The 18 real-PostgreSQL/deployed-HTTP tests ran in remote CI, explaining its
higher count and coverage. Docker Desktop's Linux engine was unavailable locally:
the local aggregate Docker gate did not pass. Remote container results supply the actual
deployment evidence, not a retroactive local pass.

The [final release audit](docs/RELEASE_AUDIT_v0.4.1.md) is the authoritative record of
commands, warning classifications, run identities, candidate digests and retained report
integrity. Engineering gates passing is not production certification or a safety guarantee.

## Compatibility and verification commands

Assessment schemas continue to distinguish `risk_score`, `risk_severity`,
`proposed_decision`, `assurance`, `final_decision` and `decision_certificate`.
Legacy aliases do not gain authorization authority. Quote-only numeric proof,
malformed Assurance or missing authorization may now be rejected where previously
accepted; callers must handle `REVIEW` / `ABSTAIN` and explicit failure states.
Mounted file secrets take precedence but do not remove separately supplied inline secrets.

Lightweight checked-in artifact gate:

```bash
python scripts/verify_v041.py
```

The complete engineering gate is `scripts/verify_v041_release.py`; individual stages
remain visible there. Artifact verification does not refit models. No nested-CV rebuild
runs during normal CI. Development reproduction instructions remain in the reference
package rather than being a release prerequisite to regenerate canonical results.

## Limitations

- development data are `DESIGN_EXPOSED` and verification/outcome availability is selective;
- development CV is not independent validation or an unbiased future performance estimate;
- scores are `UNCALIBRATED` and must not be interpreted as probabilities;
- E5 has not run and the 270-company historical exclusion remains unavailable;
- no external, production, regulatory, predictive-superiority, or safety guarantee is made.
