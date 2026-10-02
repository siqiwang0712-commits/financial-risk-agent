# FinRisk v0.4.0 — Assured Selective Financial Intelligence

**Version:** `0.4.0` · **Status:** ready for source review; prospective and external
validation remain pending.

v0.3.4 provided evidence-grounded financial-risk analysis. v0.4.0 changes the authority
model: rules, models, fusion and constrained Agent reasoning may propose a risk decision,
but only the Assurance Runtime may authorize the final decision. The Agent remains a
reasoning component; it does not decide whether its own output is trustworthy enough to
automate.

```text
prediction → proposed_decision → Assurance Runtime
           → authorized final_decision → Decision Certificate
```

The runtime invariant is: **no verified `AssuranceResult` → no authorized final
decision**.

## Assurance Runtime

Authorization evaluates separate, typed controls rather than collapsing them into one
confidence number:

- evidence assurance and machine-readable decision dependencies;
- deterministic evidence fragility;
- distribution validity;
- policy and calibration status;
- stable reason codes and fail-closed admission behavior.

The checked-in admission policy is `HEURISTIC_POLICY` / `UNCALIBRATED`. It does not emit
a probability of correctness or provide a finite-sample reliability guarantee. Missing,
incomplete, structurally invalid or policy-mismatched Assurance state cannot authorize
automation.

## Evidence assurance and fragility

Material conclusions can retain the source document and hash, location, filing period,
company, concept, unit, raw and normalized values, transformations, metric or component,
risk dimension, fusion contribution, proposal and Assurance outcome.

Fragility analysis performs deterministic leave-one-evidence-out stress tests over the
frozen dependency graph. It reports score and severity changes, proposal flips, affected
dimensions and claims, largest single-evidence impact, and flip counts/rates. It does
**not** rerun the LLM, call an external semantic provider or introduce new evidence.

Decision-Sufficient Evidence Sets identify evidence that preserves the recorded proposal.
Small sets use exact search. Larger sets use `GREEDY_APPROXIMATION`, remain marked
`exact: false`, and are not described as mathematically minimal.

## Distribution validity and reporting observability

Distribution diagnostics use `IN_REFERENCE`, `WARNING`, `OUTSIDE_REFERENCE` and
`UNKNOWN`. Worsening validity cannot increase automation eligibility; unsupported inputs
fail closed. Distribution shift means that existing Assurance claims are not asserted
outside the defined reference scope—it does not prove that a predictor is right or wrong.

The checked-in synthetic reference is explicitly `DEVELOPMENT_REFERENCE_ONLY`. It exists
to exercise development and demo paths and does not establish population
representativeness, future calibration validity or external validation.

Financial-value features and reporting-observability signals are represented separately.
Availability or missingness may affect review behavior, evidence assurance, distribution
diagnostics and research diagnostics, but it cannot silently increase core financial
severity.

## Decision Certificate and compatibility

The Decision Certificate binds material input and document identity, policy identity,
component versions, evidence dependencies, proposal and final decision, decision
provenance, replay information and certificate integrity. Deterministic verification
detects mutation of hashed material.

The certificate establishes provenance, integrity and reconstructability. It does **not**
prove that a financial conclusion is true or predictively correct.

API and frontend contracts now distinguish `risk_score`, `risk_severity`,
`proposed_decision`, Assurance, `final_decision` and `decision_certificate`. Fusion and
selective-policy `decision` fields remain documented v0.3 proposal aliases. Persisted
v0.3 DecisionBundles retain an explicit legacy verification path and do not silently gain
v0.4 authorization semantics. New v0.4 certificates require trusted policy-bound
Assurance. Operational `created_at` and `latency_ms` fields are excluded from material
replay identity; decision, evidence, policy, component and certificate content remains
hash-bound.

## Research continuity

v0.4.0 is an engineering and decision-assurance release. It does not replace or rewrite
the frozen historical evidence:

- **E4:** on 674 deterministically verified outcomes from the frozen 2,000-company
  cohort, B6 improved ranking over B0 by a limited `+0.030` AUROC. The endpoint is
  financial deterioration, not bankruptcy or default probability.
- **E4-S:** correctly specified paired inference supports the same direction while
  correcting E4's stated interpretation of its label-permutation test. Its approximately
  94%-overlapping re-execution is a near-reproduction, not an independent sample.
- **E4-R:** strong learned tabular models substantially outperform B6. Reporting and
  missingness structure carries material predictive information, and temporal features
  add little on top of the strongest static nonlinear learner. E4-R remains retrospective
  and post-hoc.
- **Agent/Hybrid:** incremental predictive value was not established; E4's fully paired
  comparison contained only five verified events.

The E4-R verifier defect found during release hardening reproduced on the untouched
pre-v0.4 baseline. Threshold extraction was corrected; frozen empirical artifacts and
results were not modified. E4-S verifies 44/44 checks and E4-R verifies 136/136 checks.

## Development validation and E5

Current maturity is:

```text
ASSURANCE RUNTIME: IMPLEMENTED
INTERNAL DEVELOPMENT VALIDATION: COMPLETE FOR THE v0.4 ENGINEERING SCOPE
PROSPECTIVE E5: PENDING / NOT_FROZEN
EXTERNAL VALIDATION: NOT ESTABLISHED
```

Internal validation covers authorization boundaries, deterministic fragility,
decision-sufficient evidence, all four distribution states, observability separation,
certificate mutation/replay behavior, API/frontend contracts, package installation and
Docker/PostgreSQL restart persistence. It is software-mechanism validation—not a
prospective outcome, calibration or external-validity study.

E5 remains `DRAFT`, `NOT_FROZEN` and
`WAITING_FOR_v0.4_ARCHITECTURE_STABILIZATION`. No cohort has been enumerated, no
predictions generated, no outcomes accessed, and no preregistration or freeze hash
created.

## Known limitations

- The policy remains `HEURISTIC_POLICY` / `UNCALIBRATED`.
- The reference distribution is synthetic and development-only.
- No prospective E5 or external validation has been completed.
- No production deployment validation, production SLA, regulatory approval or safety
  certification is claimed.
- Fragility can evaluate only dependencies represented in the frozen graph.
- Greedy sufficient-evidence output is approximate and non-minimal.
- The score is not a probability of default or bankruptcy, a credit rating, a fraud
  determination or an investment recommendation.

See the [Assurance architecture](docs/assurance_architecture.md),
[internal development validation](research/v040_development/VALIDATION_REPORT.md),
[Project Status](PROJECT_STATUS.md), [experiment results](research/EXPERIMENT_RESULTS.md)
and [research limitations](research/limitations.md).
