# FinRisk v0.3.4 Experiment Overview

This is the entry point for the current FinRisk research evidence. The active
test and publication surface is E4 on locked FinRisk v0.3.4. Earlier pilot and
v0.3.1 artifacts remain available only as historical audit records; they are
not part of the current release gate or primary result presentation.

## Evidence vocabulary

| Status | Meaning |
|---|---|
| `ESTABLISHED_E4` | Passed a prespecified E4 inference and claim gate. |
| `EXPLORATORY_E4` | Measured within frozen E4, but the prespecified power or inference gate was not met. |
| `POST_HOC` | Added after E4 outcomes were available; useful for diagnosis and planning, not confirmation. |
| `IMPLEMENTED_NOT_VALIDATED` | Engineering exists, but the corresponding empirical claim has not been tested. |
| `NOT_TESTED` | No qualifying experiment has been completed. |

All reported risk scores remain `UNCALIBRATED` heuristic indices. E4 evaluates
ranking against a deterministic forward financial-deterioration endpoint, not
bankruptcy, default, credit loss or insolvency probability.

## Current experiment surface

| Study | Purpose | Data and scale | Result status | Main conclusion |
|---|---|---|---|---|
| E4-A external validation | Out-of-time, company-disjoint deterministic comparison | 2,000 FY2024 filers; 674 verified outcomes; 235 events | P1 `ESTABLISHED_E4` | B6 improved B0 in paired AUROC by +0.030 (95% CI +0.014 to +0.048; Holm-adjusted p=0.0015). |
| E4-B structured comparison | Compare deterministic, traditional, Agent and fixed Hybrid systems on identical verified observations | 50 frozen cases; 18 verified; 5 events | Agent/Hybrid results `EXPLORATORY_E4` | Local Agent and Hybrid incremental value was not established. |
| E4 robustness and integrity | Test missingness, sector, thresholds, attrition, Agent stability, batching and source concordance | Frozen E4 artifacts and prespecified checks | Mixed confirmatory/supporting evidence | Reproduction passed, while verification selection and Agent power remain material limitations. |
| E4 post-hoc audit | Quantify verification bias, schema, calibration, batching and concordance weaknesses | Frozen E4 artifacts; no redefinition of E4 | `POST_HOC` | E4 remains valid within its narrow P1 claim. |
| `ChatGPT5.6 Sol` comparator | Structured A0/A1/A2 comparison executed by Codex sub-Agents | 50 frozen anonymous cases; 150/150 judgments; 18 verified; 5 events | `POST_HOC` | Point estimates are insufficiently powered and do not change E4. The name is an internal codename, not an official model identity. |
| E5 | Future confirmatory study | A new untouched time window is required | Protocol only / `NOT_TESTED` | No E5 cohort, predictions, labels or results exist. |

## What E4 supports

- Temporal structured signal B6 showed a small positive paired AUROC
  improvement over B0 on the prespecified, deterministically verified E4-A
  subset.
- Deterministic E4 stages reproduced byte-identically, and frozen Local Agent
  responses replayed to the same parsed predictions.
- Public claims, figures and result tables are generated from the canonical E4
  summary and protected by explicit claim gates.

## What it does not support

- A calibrated probability of default or a validated bankruptcy model.
- Population-wide performance beyond the 674 deterministically verifiable
  observations; weighting sensitivity does not remove selection bias.
- Incremental value from the E4 Local Agent or Hybrid; those comparisons had
  only five paired events.
- External validation of full-document grounding, MD&A/Risk-Factor reasoning,
  planner/reflection behaviour or regulatory/production fitness.
- A capability claim about a named commercial model. `ChatGPT5.6 Sol` is a
  project-internal display name for the post-hoc Codex sub-Agent comparator;
  its exact underlying model ID was not exposed by the platform.

## Reading order

1. [Experiment results](EXPERIMENT_RESULTS.md) — current E4 numbers and conclusions.
2. [E4 validation report](e4/public/VALIDATION_REPORT.md) — canonical design and result.
3. [E4 post-completion audit](e4_posthoc/AUDIT_REPORT.md) — limitations and post-hoc diagnostics.
4. [Reproducibility guide](EXPERIMENT_REPRODUCIBILITY.md) — current release checks and artifact boundaries.
5. [E5 protocol](e5/STUDY_PROTOCOL_DRAFT.md) — requirements for the next confirmatory study.
