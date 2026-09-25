# E4 Post-completion Audit Report

Status: **E4 VALID**

Audit scope: frozen E4 artifacts, methods, statistics, Agent runtime, source concordance, reproducibility, claims, and public-data boundaries.

## Independent integrity result

The audit re-read the canonical files rather than relying on the README. The
feature, label, and prediction hashes match their freeze records; all 2,000
observations are aligned; 10,200 predictions are present; non-VERIFIED outcomes
remain null; and P1 independently matches the frozen ΔAUROC `+0.0303058`. No
change to the E4 cohort, predictions, labels, hypotheses, prompt, threshold,
model, H0 weights, or primary statistics was made.

No issue capable of reversing the frozen P1 calculation was found. The E4
claim remains narrow: B6 showed a positive paired ranking improvement over B0
on the prespecified, deterministically verified subset.

## CRITICAL

None found.

## MAJOR

### Selective outcome verification

- **Issue:** Only 674/2,000 observations were deterministically verified.
- **Evidence:** A prediction-time-only, five-fold cross-fitted verification
  propensity model achieved AUROC `0.740`. VERIFIED observations differ from
  REVIEW/INSUFFICIENT observations in company size, missingness, fact count,
  filing timing, and B0/B6 distributions. Several absolute SMDs exceed `0.4`.
- **Consequence:** Unweighted E4 performance does not identify performance for
  all 2,000 companies.
- **Fixable now:** No.
- **Action:** Added group diagnostics and stabilized inverse-propensity
  sensitivity with untruncated, cap-10, cap-5, p99, and p95 weights.
- **Remaining limitation:** MAR is not established. The untruncated maximum
  weight is `24.63` and ESS is only `247.2`. Weighted B6−B0 remained positive
  (`+0.034` to `+0.042`), but this is sensitivity analysis only.

### Agent power and endpoint attrition

- **Issue:** P2/P3 contain five paired positive events.
- **Evidence:** The exact funnel is `50 selected → 50 packet available → 50
  callable → 45 valid A2 schemas → 18 endpoint VERIFIED → 16 paired → 5
  events`. Endpoint attrition removes 32 cases; A2 failure removes two more
  among verified cases; comparison intersection removes none beyond A2.
- **Consequence:** H0 versus B0 and H0 versus A2 cannot establish improvement.
- **Fixable now:** No.
- **Action:** Added a machine-readable, cause-separated funnel.
- **Remaining limitation:** A new future period needs a substantially larger
  Agent cohort and more verified events.

### Model-capacity and scope boundaries

- **Issue:** The only installed local model was Qwen2.5 0.5B Q4_K_M.
- **Evidence:** Ollama inventory contained no stronger model. The user
  authorized the online comparator, but the execution environment denied the
  external packet transfer under its data-egress policy.
- **Consequence:** E4 cannot support “LLMs/Agents do not add value.”
- **Fixable now:** Not without changing infrastructure after outcome exposure.
- **Action:** No fallback or post-outcome model download was used. A secret-safe
  local GPT-5 launcher and comparator client were prepared and statically
  tested, but no API request occurred. The stronger-local and external GPT-5
  studies remain NOT_TESTED. A separate Codex sub-Agent comparator was later
  run under the project-internal display name `ChatGPT5.6 Sol`; its 150/150
  structured outputs are `POST_HOC`, the exact underlying model ID was not
  exposed, and only 18 cases/five events were verified.
- **Remaining limitation:** E5 must freeze a stronger model before outcome
  access.

### Endpoint and full-Agent interpretation

- **Issue:** The endpoint is deterministic financial deterioration, and FSDS
  does not supply the full narrative corpus.
- **Evidence:** Labels come from `deterministic_forward_outcome_rule_v1`; Agent
  packets contain structured facts/features, not full MD&A/Risk Factors.
- **Consequence:** No bankruptcy/default probability or full FinancialRiskAgent
  validation claim is supported.
- **Fixable now:** No.
- **Action:** README wording was narrowed and evidence statuses were added in a
  post-E4 overlay.
- **Remaining limitation:** Separate adjudicated endpoint and narrative studies
  are required.

## MODERATE

### Batch-context sensitivity

The batch-single absolute difference has median `0.010`, mean `0.101`, p90
`0.314`, p95 `0.418`, and maximum `0.770`. Spearman and Kendall correlations
are both approximately `0.313`; one threshold flip occurred. Thus 96.6%
binary agreement must not be presented as ranking stability. A post-hoc
batch-size-2 run over A0/A1 produced 20 valid results with mean difference
`0.169` versus single-case and `0.158` versus original batches. It changed no
E4 prediction.

### Schema diagnostics

All five frozen failures were A2 single-case failures after two attempts, but
E4 retained only `TypeError`, not the invalid response. Root cause cannot be
recovered. Future runtime now emits deterministic error codes and retains the
masked invalid response plus a canonical hash. No semantic repair or model
imputation was introduced.

### Calibration

Every score remains `UNCALIBRATED`. Post-hoc descriptive diagnostics show B0
ECE `0.167` and B6 ECE `0.130`; Agent scores are concentrated near one and have
much larger score/prevalence gaps. These calculations do not calibrate any
model and cannot turn a score into probability.

### SEC–Zenodo concordance

The audit reconstructed all 17,757 comparisons. Of 1,624 values differing by
more than 5%, 1,185 had period mismatch, 53 had sign mismatch, 17 involved
duplicate candidates, one looked like unit scaling, and 428 remain compatible
with taxonomy/definition/restatement differences. Equity was the weakest
metric (`85.3%` within 5%). A POST-E4 code fix now requires exact period match
and rejects conflicting duplicates. Recalculation under that corrected rule
retained 15,216 comparisons across 1,422 companies and found 97.1% within 5%.
This changes only future concordance analysis, never E4 scoring or P1.

### Fusion

The 0.5/0.5 H0 choice remains frozen and valid as a transparent prespecification.
The post-hoc weight grid is diagnostic only; with 16 observations and five
events it cannot select a future production weight.

### Codex comparator runtime identity

The separate Codex sub-Agent comparator completed all 150 structured judgments
under the project-internal display name `ChatGPT5.6 Sol`. The platform exposed
neither an exact underlying model ID nor a complete system-prompt/runtime
attestation. Its outputs and packet hashes are frozen and auditable, but the
inference call is not independently byte-reproducible and cannot support a
named-model capability claim. With only 18 verified cases and five events, its
reported A0/A1/A2/H0 metrics remain `POST_HOC`, `UNCALIBRATED`, and
insufficiently powered.

## MINOR

The audit added a secret-free environment manifest covering Python packages,
OS/architecture, locale, Docker engine, images, Ollama/model digests, seeds,
and serialization rules. Because it was captured after E4, it supplements but
does not replace the original frozen runtime manifest. No prospectively frozen
reserve cohort was found; unused E4 companies are not eligible for retrospective
confirmatory reuse.

## Engineering and documentation actions

- Added deterministic post-hoc audit runner and tests.
- Added schema failure classification and future failure evidence retention.
- Corrected future SEC–Zenodo matching semantics.
- Added verification-bias, funnel, batch, fusion, calibration, concordance, and
  environment artifacts under `research/e4_posthoc/`.
- Preserved the canonical `research/e4/` results and recorded evidence statuses
  in a post-E4 overlay rather than rewriting the frozen summary.
- Added a fully covered Codex sub-Agent comparator with explicit internal-name,
  model-identity, reproducibility, and post-hoc limitations.
- Prepared an outcome-blind E5 protocol; no E5 results were fabricated.

The complete issue inventory is in `limitations_registry.json`.
