# FinRisk v0.4 Assurance Architecture

Status: **IMPLEMENTED — INTERNAL DEVELOPMENT VALIDATION — NOT EXTERNALLY VALIDATED**

This document is the authoritative design reference for the v0.4 decision-assurance
runtime. It describes software semantics, not an empirical claim that the decisions are
correct.

## Problem definition

Financial-risk components can calculate a score, identify a signal or propose a
disposition without establishing that the available evidence is strong enough for the
system to issue that disposition. v0.4 therefore separates two questions:

1. **Prediction:** what risk disposition do the available analytical components propose?
2. **Authorization:** is that proposal adequately supported under the active assurance
   policy and its stated maturity boundary?

The invariant is:

```text
No valid AssuranceResult
→ no authorized final decision
```

`authorized_final_decision()` verifies the type and content hash of the
`AssuranceResult`. Both the deterministic API path and Agent path use this publication
boundary.

## Runtime architecture

```text
filing
  → ingestion / normalization
  → metrics / rules / models / constrained LLM / Agent
  → risk fusion
  → proposed_decision
  → AssuranceEngine
       ├─ evidence assurance
       ├─ evidence fragility
       ├─ distribution validity
       └─ admission policy
  → final_decision
  → Decision Certificate
```

The calculation layer owns `risk_score`, `risk_severity` and
`proposed_decision`. It does not own `final_decision`. The Assurance layer does not
recalculate financial arithmetic or ask the LLM to reconsider its answer.

The implementation lives in `backend/finrisk/assurance/`:

| Module | Responsibility |
|---|---|
| `domain.py` | typed states and outputs |
| `engine.py` | sole authorization boundary |
| `policy.py` | versioned, content-hashed admission policy |
| `evidence.py` | verified path accounting and deterministic dependency extraction |
| `fragility.py` | evidence ablation and sufficient-evidence search |
| `shift.py` | financial/reporting split and reference-distribution diagnostics |
| `certificate.py` | Decision Certificate verification |
| `reason_codes.py` | stable machine-readable explanations |

## Decision authority

Rules, models, fusion and Agent review may propose `PASS`, `FLAG`, `REVIEW` or
`ABSTAIN`. A v0.3 compatibility field named `decision` remains on fusion and selective
policy outputs, but it is explicitly marked as a proposal alias. Those objects contain no
authorized `final_decision`.

`AssuranceEngine.evaluate()` returns an `AssuranceResult` containing:

- proposed and final decisions;
- automation eligibility;
- separate evidence, fragility and distribution results;
- policy and calibration maturity;
- stable reason codes;
- policy version and policy hash;
- an authorization-record hash.

If assurance data is absent or invalid, publication fails. Missing verified evidence can
force `ABSTAIN`; fragility, distribution or runtime concerns can force `REVIEW`. A proposal
that is already `ABSTAIN` remains withheld.

## Assurance states

### Evidence assurance

Material paths are evaluated as `VERIFIED`, `PARTIAL`, `INSUFFICIENT` or `UNKNOWN`.
A verified path requires complete verified provenance for its declared inputs. Removing a
verified evidence item invalidates every dependent path while preserving the original
material-path denominator; evidence removal therefore cannot improve assurance.

The path representation can carry:

- source document and source hash;
- page/location and filing period;
- company, XBRL concept and unit where available;
- raw and normalized values;
- transformation/metric;
- rule or model;
- risk dimension and fusion contribution;
- proposed decision and assurance outcome.

The relationship is described as a **decision dependency** or **computational
contribution**, not a causal effect.

### Evidence fragility

Fragility analysis freezes the existing dependency graph, removes one evidence node at a
time and recomputes deterministic downstream fusion only. It does not:

- rerun an LLM;
- call an external semantic provider;
- ingest new evidence;
- mutate the source assessment.

For each ablation it records score delta, severity change, proposed-decision change,
final-decision impact, affected dimensions and affected claims. Aggregate diagnostics
include largest single-evidence impact, decision-flip count and decision-flip rate. States
are `STABLE`, `SENSITIVE`, `FRAGILE` and `NOT_ESTIMABLE`.

### Decision-Sufficient Evidence

For at most the policy's exact-search node ceiling, the runtime evaluates evidence subsets
in increasing cardinality and returns an `EXACT` decision-preserving set. Above that
ceiling it uses deterministic greedy removal and reports `GREEDY_APPROXIMATION` with
`exact: false`. An approximate set is never described as mathematically minimal.

### Distribution validity

Distribution validity asks whether an observation lies within a frozen development or
validation reference profile. It does not prove that a model is correct or wrong.

States are `IN_REFERENCE`, `WARNING`, `OUTSIDE_REFERENCE` and `UNKNOWN`. Diagnostics may
cover feature bounds, sector scope, required-feature availability and reporting
availability. Outside-reference and unknown states fail closed under the default policy:
automation is withheld and an actionable proposal is routed to `REVIEW` or `ABSTAIN`.

> Existing assurance claims are not asserted outside the validated reference
> distribution.

The repository contains a hash-bound synthetic profile scoped as
`DEVELOPMENT_REFERENCE_ONLY`. It exists only to exercise all validity states in the demo
and deterministic tests; it has one synthetic source fixture and is not representative of
an issuer population. Runtime inputs without an explicitly supplied supported profile
report `UNKNOWN`. No empirical or externally validated v0.4 reference profile exists.

## Financial values and reporting observability

`FinancialFeatureVector` contains financial values. `ReportingObservabilityVector`
contains only availability flags. The latter may affect evidence assurance, distribution
validity, diagnostics and review routing, but it is never passed into financial severity
fusion.

This preserves future retrospective comparisons of:

- financial values only;
- reporting missingness only;
- combined inputs;
- harmonized availability.

No new confirmatory missingness result is claimed in v0.4.

## Policy and calibration maturity

The policy declares one of:

- `HEURISTIC_POLICY`;
- `CALIBRATED_INTERNAL`;
- `VALIDATED_EXTERNAL`.

The checked-in default is `HEURISTIC_POLICY`; runtime calibration status is
`UNCALIBRATED`. Reliability is therefore absent, probability is always `null`, and
automation is withheld. The architecture can accept a genuinely calibrated policy later,
but it does not claim finite-sample, conformal or external guarantees today.

## Decision Certificate

v0.4 extends the existing `DecisionBundle` instead of replacing it. A certificate includes:

- input and document digests;
- proposed and final decisions;
- complete assurance result;
- decision-sufficient evidence;
- policy version/hash and calibration status;
- component versions and deterministic replay metadata;
- certificate version and certificate hash.

`bundle_hash` remains as a compatibility alias for `certificate_hash`. Verification
canonicalizes all hashed content. Changing a nested assurance field, decision, policy,
component version or evidence path invalidates the hash. Persisted v0.3 bundles retain a
legacy verification path so historical records remain readable.

## API and UI contract

Assessment responses keep these quantities distinct:

```text
risk_score
risk_severity
proposed_decision
assurance
final_decision
decision_certificate
```

`confidence` remains a legacy evidence-quality index, not a probability. The Workbench
shows the proposal, Assurance status and final decision as separate headline elements and
uses progressive disclosure for fragility, sufficient evidence, distribution validity and
certificate metadata.

## Replay

Snapshots hash frozen inputs and material outputs. Certificates are separate artifacts
because their output digest necessarily depends on the snapshot output. Replaying
identical inputs, documents, component versions and policy produces identical material
decision output and certificate hashes; wall-clock creation time is excluded from the
certificate hash.

## Research maturity and limitations

| Area | v0.4 status |
|---|---|
| Assurance Runtime | implemented |
| Deterministic unit/integration validation | complete for v0.4 release scope |
| Internal development validation | complete |
| Synthetic development reference | implemented; development only |
| Calibrated admission policy | not established |
| Frozen empirical/external reference distribution | not established |
| Prospective E5 validation | pending |
| External/production/regulatory validation | not established |

The runtime can detect conditions under which its own policy refuses authorization. That
does not establish that an authorized financial conclusion is true, causal or suitable for
a regulated decision. See [research limitations](../research/limitations.md) and the
[capability maturity matrix](capability_maturity_matrix.md).
