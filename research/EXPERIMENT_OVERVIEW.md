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
| `POST_E4_STATISTICAL_AUDIT` | Produced by E4-S, the audit of E4's frozen inference. It re-checks E4 and may state what E4's own procedure does and does not test; it cannot change an E4 number. |
| `POST_HOC_AUTOMATED_ROBUSTNESS` | Produced by E4-R, the automated robustness and competitive-baseline study. Retrospective, run on E4-S's replication packet, prespecified separately from E4. |
| `REPLICATION_COHORT_INFERENCE` | Real paired data from an independent re-execution of the frozen pipeline, on a cohort that is ~94% but not fully overlapping with E4's. |
| `SURROGATE_RECONSTRUCTION` | Data reconstructed to match published summary statistics. Diagnostic only; never quoted as an E4 result. |
| `NOT_INDEPENDENTLY_REPRODUCIBLE` | Cannot be re-derived from published artifacts. |
| `IMPLEMENTED_NOT_VALIDATED` | Engineering exists, but the corresponding empirical claim has not been tested. |
| `NOT_TESTED` | No qualifying experiment has been completed. |

All reported risk scores remain `UNCALIBRATED` heuristic indices. E4 evaluates
ranking against a deterministic forward financial-deterioration endpoint, not
bankruptcy, default, credit loss or insolvency probability.

## Current experiment surface

Rows are ordered by dependency: each study reads the row above it, and E4-S and
E4-R sit between E4 and E5 because they exist to make E5 designable.

| Study | Purpose | Data and scale | Result status | Main conclusion | Report |
|---|---|---|---|---|---|
| E4-A external validation | Out-of-time, company-disjoint deterministic comparison | 2,000 FY2024 filers; 674 verified outcomes; 235 events | P1 `ESTABLISHED_E4` | B6 improved B0 in paired AUROC by +0.030 (95% CI +0.014 to +0.048; Holm-adjusted p=0.0015). | [Validation report](e4/public/VALIDATION_REPORT.md) |
| E4-B structured comparison | Compare deterministic, traditional, Agent and fixed Hybrid systems on identical verified observations | 50 frozen cases; 18 verified; 5 events | Agent/Hybrid results `EXPLORATORY_E4` | Local Agent and Hybrid incremental value was not established. | [Experiment results](EXPERIMENT_RESULTS.md) |
| E4 robustness and integrity | Test missingness, sector, thresholds, attrition, Agent stability, batching and source concordance | Frozen E4 artifacts and prespecified checks | Mixed confirmatory/supporting evidence | Reproduction passed, while verification selection and Agent power remain material limitations. | [Post-completion audit](e4_posthoc/AUDIT_REPORT.md) |
| E4 post-hoc audit | Quantify verification bias, schema, calibration, batching and concordance weaknesses | Frozen E4 artifacts; no redefinition of E4 | `POST_HOC` | E4 remains valid within its narrow P1 claim. | [Post-completion audit](e4_posthoc/AUDIT_REPORT.md) |
| `ChatGPT5.6 Sol` comparator | Structured A0/A1/A2 comparison executed by Codex sub-Agents | 50 frozen anonymous cases; 150/150 judgments; 18 verified; 5 events | `POST_HOC` | Point estimates are insufficiently powered and do not change E4. The name is an internal codename, not an official model identity. | [Comparator methodology](e4_posthoc/model_capacity/sol_codex_agent/METHODOLOGY.md) |
| E4-S statistical audit | Re-test E4's primary inference under a correctly specified correlated-model test, and re-execute the frozen pipeline from public inputs | E4's published summary; a 675-observation / 235-event re-execution cohort | `POST_E4_STATISTICAL_AUDIT` | E4's conclusion survives; its stated justification does not. E4's exact rows remain unpublished. | [E4-S audit report](e4_statistical_audit/AUDIT_REPORT.md) |
| E4-R automated robustness | Test whether B6's temporal gain is robust, and whether conventional tabular learning explains or beats it | Same 675 / 235 cohort; 11 nested-CV baselines, 7 ablations, 20,000-replicate bootstraps | `POST_HOC_AUTOMATED_ROBUSTNESS` | Strong tabular models beat B6 decisively, but a material share of that advantage is reporting structure rather than financial-value signal. | [E4-R final report](e4r_automated_robustness/FINAL_REPORT.md) |
| E5 | Future confirmatory study | A new untouched time window is required | Protocol only / `NOT_TESTED` | No E5 cohort, predictions, labels or results exist. | [E5 protocol](e5/protocol/STUDY_PROTOCOL.md) |

## What E4 supports

- Temporal structured signal B6 showed a small positive paired AUROC
  improvement over B0 on the prespecified, deterministically verified E4-A
  subset.
- Deterministic E4 stages reproduced byte-identically, and frozen Local Agent
  responses replayed to the same parsed predictions.
- Public claims, figures and result tables are generated from the canonical E4
  summary and protected by explicit claim gates.
- The direction of that improvement also survives a correctly specified paired
  DeLong test (E4-S) and a full competitive-baseline sweep (E4-R).

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

## What the post-hoc chain adds — and what it cannot add

E4-S and E4-R are the two post-hoc studies downstream of E4. They are named
after what they read: `S` is the statistical audit of E4's own inference, `R` is
the automated robustness and competitive-baseline study that runs on `S`'s
replication packet. Neither one modifies E4, neither creates confirmatory
evidence, and neither licenses an E5 claim.

- **E4-S.** E4's published P1 p-value tests `H0_independence`, not the
  `H0_equality` claim E4 attaches to it, and it sits at the attainable floor
  `1/2001`. At E4's design point the procedure is nonetheless close to nominal
  (measured size 0.025 against α = 0.05, power 0.930 against DeLong's 0.935), so
  E4's numbers are unaffected and only its justification changes. E4's exact
  paired rows remain `NOT_INDEPENDENTLY_REPRODUCIBLE`.
- **E4-R.** Strong tabular learning beats B6 decisively on the same observations
  (+0.180 AUROC for the prespecified boosting challenger). The B6 − B0 gain is
  robust in sign but entirely mechanical — removing the temporal block makes B6 a
  strictly rank-equivalent transform of B0 — and a material share of the learned
  advantage is reporting/missingness structure rather than financial-value
  signal.

The one design conclusion both studies produce is stated in
[the results summary](EXPERIMENT_RESULTS.md): E5's primary benchmark can no
longer be B0.

## Reading order

1. [Experiment results](EXPERIMENT_RESULTS.md) — current E4 numbers and conclusions.
2. [E4 validation report](e4/public/VALIDATION_REPORT.md) — canonical design and result.
3. [E4 post-completion audit](e4_posthoc/AUDIT_REPORT.md) — limitations and post-hoc diagnostics.
4. [E4-S statistical audit](e4_statistical_audit/README.md) — what E4's inference does and does not test.
5. [E4-R robustness study](e4r_automated_robustness/README.md) — robustness and competitive baselines.
6. [Reproducibility guide](EXPERIMENT_REPRODUCIBILITY.md) — current release checks and artifact boundaries.
7. [E5 protocol](e5/README.md) — requirements for the next confirmatory study.
