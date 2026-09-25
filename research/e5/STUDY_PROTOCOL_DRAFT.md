# E5 Confirmatory External Validation — Protocol Draft

Status: **DRAFT — NOT FROZEN — NO RESULTS**

## Purpose

E5 will prospectively test structured temporal, stronger-Agent, and fixed
hybrid comparators against a predefined financial-deterioration endpoint in a
new, untouched time window. It will not treat E4 post-hoc findings as
confirmation and will not claim bankruptcy/default probability validation.

## Required novelty and isolation

- Feature and outcome periods must be later than E4 and unavailable when the
  protocol, cohort, packets, predictions, and model outputs are frozen.
- Companies must be disjoint from all E1–E4 and historical validation cohorts.
- No unused E4 company can be called prospective merely because it was not in
  E4-A; E4 outcomes and design feedback are already known.
- Prediction containers receive feature data only. Outcome containers start
  only after a content-addressed prediction freeze.

## Confirmatory systems

- B0 and B6 remain locked reference systems unless a separately versioned
  source release is named before data access.
- One stronger instruct model is selected using availability, structured-output
  reliability, context, reproducibility, and hardware feasibility—never E5
  outcome performance.
- A0/A1/A2 schemas and prompts are frozen after outcome-blind smoke tests.
- One primary Agent representation and one hybrid formula are nominated before
  prediction. Any other variants are secondary.
- Hybrid weights must come from historical development data or a transparent
  prespecified rule, not E4/E5 test labels.

## Primary hypotheses

The final freeze may include at most three multiplicity-controlled primary
comparisons. A recommended structure is: B6 vs B0, stronger A2 vs B0, and fixed
Hybrid vs both B0 and A2 using a hierarchical gate. Exact estimands, direction,
and multiplicity procedure must be frozen before cohort construction.

## Agent reliability gates

- At least 99% schema-valid output in outcome-blind qualification packets.
- Exact input/output ID equality, deterministic retry, and bisect recovery.
- Raw masked response retention with error code and response hash.
- Pre-outcome batch-size sensitivity at sizes 1, operational-small, and target;
  freeze an acceptable rank-correlation and score-difference tolerance.
- No web, identity, future data, tools, repository, or arbitrary filesystem.

## Outcome and coverage

- Use a versioned deterministic deterioration endpoint with an adjudication
  protocol for REVIEW cases that is blind to system scores.
- Prespecify minimum verified coverage and compare prediction-time covariates
  across VERIFIED/REVIEW/INSUFFICIENT groups.
- Verification weighting may be prespecified as sensitivity only; it cannot
  replace missing labels without defensible identification assumptions.

## Sample-size gate

The Agent paired cohort should target at least 1,200 selected companies. At the
E4 verified rate (33.7%) and event rate (34.9%), this projects roughly 404
verified observations and 141 events. The study must not unlock outcomes unless
the frozen cohort is large enough to plausibly deliver at least 100 paired
events after schema and endpoint attrition. The final calculation must be
updated using outcome-blind operational rates and a prespecified effect size,
not E4 test optimization.

## Calibration track

If probability calibration is attempted, development, calibration, and final
validation companies/time windows must be distinct. Calibration method and
bins are frozen on the calibration split; the final validation split reports
calibration intercept/slope, Brier, ECE, and decision curves without refitting.
Otherwise all scores remain `UNCALIBRATED`.

## Narrative/document track

This is separate from structured E5 unless complete filing text is available.
It requires frozen MD&A, Risk Factors, footnotes, and auditor text; independent
dual annotation/adjudication; claim-level grounding, extraction, contradiction,
and abstention metrics; and company/time-disjoint evaluation.

## Reproducibility and claims

Freeze source commit, dependency lock, containers, model/tokenizer/digest,
quantization, hardware-relevant parameters, prompts, packets, batching, seeds,
thresholds, hypotheses, analysis code, and public claim gates. Deterministic
outputs must replay byte-identically; stochastic model behavior is evaluated
separately. Negative results are valid outcomes.
