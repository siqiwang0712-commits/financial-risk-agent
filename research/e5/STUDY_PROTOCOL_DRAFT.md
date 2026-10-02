# E5 — Prospective Validation of Assured Selective Financial Decisions

Status: **DRAFT — WAITING FOR v0.4 ARCHITECTURE STABILIZATION**

This is not a frozen preregistration. No cohort has been enumerated, no predictions have
been generated, and no future outcomes have been accessed. The design must not receive a
final hash until v0.4 interfaces, policy semantics and certificate replay are stable.

## Purpose

E5 will prospectively evaluate whether Assurance improves the safety and utility of
selective financial decisions on a new, company-disjoint future cohort. It will not treat
E4 post-hoc findings as confirmation and will not claim bankruptcy/default probability
validation.

E5 separates predictive ranking from decision authorization. A stronger AUROC does not by
itself validate evidence support, automation eligibility, abstention behavior or a final
decision policy.

## Required novelty and isolation

- Feature and outcome periods must be later than E4 and unavailable when the protocol,
  cohort, packets, predictions and certificates are frozen.
- Companies must be disjoint from E1–E4, public pilot, historical development data and
  the unpublished prior 270-CIK cohort.
- No unused E4 company is prospective merely because it was not selected for E4-B.
- Prediction containers receive feature data only. Outcome access begins only after a
  content-addressed prediction and certificate freeze.
- `research/e4/_cache/previous_270.json` remains a fail-closed cohort blocker.

## Future comparison framework

Exact implementations are intentionally open until v0.4 stabilization. The freeze must
nominate one member of each required arm without looking at E5 outcomes:

| Arm | Purpose |
|---|---|
| Strong tabular predictor | competitive predictive reference consistent with E4-R |
| Strong tabular + selective policy | isolates the value of selective admission from Agent reasoning |
| Raw Agent | measures unconstrained proposal behavior; never final authority |
| Agent + evidence verification | isolates evidence admission from full Assurance |
| Full FinRisk Assurance | evidence assurance + fragility + distribution validity + admission policy |

B0 and B6 remain historical reference arms. They may be reported, but the primary design
must not imply B6 is the strongest available tabular comparator.

## Estimands to freeze later

The final protocol must define separate, multiplicity-controlled estimands for:

- predictive discrimination on the common evaluable cohort;
- calibrated risk, only if three disjoint development/calibration/validation splits exist;
- risk–coverage and error–coverage behavior;
- unsafe automation and unsupported-decision rates;
- review/abstention utility and coverage;
- evidence-path correctness, fragility and certificate replay integrity.

No current number is a target result. Minimum meaningful effects and sample size remain
open design choices and must be frozen before cohort construction.

## Assurance qualification gates

Before protocol freeze, synthetic and historical outcome-blind fixtures must establish:

- no runtime path can publish a final decision without `AssuranceResult`;
- evidence removal cannot improve evidence assurance;
- fragility replay is deterministic and invokes no LLM/provider;
- outside-reference status never increases automation eligibility;
- reporting observability cannot raise financial severity;
- `UNCALIBRATED` outputs expose neither probability nor reliability claims;
- certificate mutations fail verification;
- identical frozen inputs, documents, components and policy replay identically.

These are software qualification gates, not E5 outcomes.

## Outcome and coverage

The endpoint remains a versioned financial-deterioration endpoint, not bankruptcy,
default or credit loss. REVIEW cases require blinded adjudication. The protocol must
report VERIFIED/REVIEW/INSUFFICIENT coverage and prediction-time covariates. Reweighting
may be a sensitivity analysis only; it cannot replace missing outcomes.

## Calibration and distribution validity

If calibration is attempted, development, calibration and final validation companies/time
windows must be distinct. Method, bins and decision thresholds are frozen before final
validation. Otherwise all scores remain `UNCALIBRATED`.

The reference-distribution profile must be built without E5 outcomes and frozen before
prediction. Shift detection means the assurance claim is withheld outside scope; it does
not prove the predictor wrong. Online adaptive conformal learning is outside this design.

## Governance and claims

The existing staged harness, outcome isolation, blinded adjudication and hash-chain ideas
under `protocol/` remain useful. They must be updated to the five-arm Assurance framework
before use. Negative or mixed findings are valid outcomes.

E5 may establish prospective performance only if every freeze and outcome-isolation gate
passes. It cannot establish production, regulatory or universal validity from one cohort.
