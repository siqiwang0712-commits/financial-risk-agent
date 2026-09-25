# E4 — Large-Scale Comparative External Validation of Structured Financial Reasoning

## Frozen purpose and source

E4 evaluates the exact FinRisk `v0.3.4` implementation at commit
`4273b070678240fe7cbdf01a17527afcc71c500e`. It is an out-of-time,
company-disjoint comparison of structured financial risk ranking. It does not
modify or regenerate E1, E2, E3, `public_v1`, historical manifests, or the
release tag.

FinRisk scores and Agent scores remain explainable heuristic risk indices.
They are not probabilities of default. Reliability remains `UNCALIBRATED`.

## Data and isolation

Feature observations are original FY2024 Form 10-K filings filed from
2024-07-01 through 2025-06-30 in SEC FSDS `2024q3`–`2025q2`. FY2023
comparatives are admitted only when reported in the same FY2024 accession.
Outcome archives `2025q3`–`2026q2` are unavailable to prediction containers
until every prediction is frozen. Every ZIP must pass SHA-256, CRC, member,
size, and integrity checks.

The optional Zenodo snapshot is used only for independent SEC measurement
concordance. It is forbidden for cohort selection, imputation, features,
training, scoring, thresholds, and labels.

## Cohort

Candidates require a valid original FY2024 10-K, non-financial SIC, valid CIK
and accession, at least one computable B0 component, and at least one
same-filing temporal component. E1/E2/E3, `public_v1`, historical development
companies, and the exact prior 270-CIK external-validation cohort are excluded.

If no more than 2,000 candidates are eligible, all are used. Otherwise,
proportional SIC-stratum quotas are allocated by largest remainder and records
within each stratum are selected by ascending SHA-256 of
`finrisk-e4-cohort-v1:<CIK>`. This algorithm and salt are frozen before cohort
construction. E4-B contains at most 50 E4-A companies selected by the frozen
Agent hash, reflecting the measured CPU-only local-runtime budget. Stability
and batch-sensitivity subsets contain at most 20 and 10 companies respectively.

## Comparators

- B0: committed `ratio_risk_score`.
- B1: committed `LogisticBaseline`, fitted only on verified historical
  development observations.
- B2: committed `RuleEngine` and rules.
- B3: committed Altman, Beneish, Piotroski, and Ohlson implementations with the
  existing research aggregation semantics. Missing required model inputs are
  not imputed.
- B6: committed `temporal_risk_score`.
- A0: raw FY2024 and same-filing FY2023 facts only.
- A1: engineered metrics, deltas, and missingness only.
- A2: raw facts, engineered evidence, and individual traditional-model outputs;
  no B0/B2/B6/Hybrid final score.
- H0: exactly `0.5 × B6 + 0.5 × A2`.

Every prediction uses threshold 0.5 and the common `PredictionRecord` schema.
No E4 label may be used for fitting, selection, prompt/model choice,
calibration, thresholding, or hybrid weighting.

## Local Agent boundary

All A0/A1/A2 calls pass over HTTP through the independent Local Agent API.
The frozen backend is Qwen2.5 0.5B Instruct, GGUF Q4_K_M, served by Ollama
0.12.3 on CPU with a 4,096-token context, temperature 0, seed 20260924, and
eight inference threads. The API and backend run on a Docker internal network
with read-only root filesystems. The Agent sees only anonymized research
packets and has no internet, SEC/Zenodo/outcome mount, repository mount, tools,
shell, or arbitrary host-filesystem access.

Batches target 25 cases but are shortened before freeze to stay within 70% of
the model context budget. Each request contains one representation. A failed
batch is retried unchanged once, then deterministically bisected left/right
until a single permanent failure is recorded as `AGENT_FAILED`. Prompts,
packets, hashes, order, requests, responses, and model identity are frozen.

## Hypotheses and statistics

The only primary comparisons are P1 B6 vs B0, P2 H0 vs B0, and P3 H0 vs A2.
P2/P3 and the README comparison table use the same E4-B paired observations.
All other comparisons are secondary or exploratory.

Primary metrics are AUROC and PR-AUC, with event prevalence reported beside
PR-AUC. Secondary metrics are balanced accuracy, recall, specificity,
precision, F1, FNR, confusion matrix, and coverage. Brier is descriptive only.
Uncertainty uses 5,000 company-level bootstrap replicates; inference uses 2,000
label permutations and Holm adjustment across P1/P2/P3. Inference requires at
least 20 events and 10 event companies; otherwise it is explicitly
exploratory. Thresholds 0.2–0.8 are sensitivity analyses, never retuning.

Robustness covers 10%/30% metric and raw-fact missingness, sector
heterogeneity, threshold sensitivity, endpoint attrition, Agent stability,
batch-context sensitivity, Agent failure coverage, and SEC–Zenodo concordance.
Subgroups below 20 observations, five events, or five non-events are
descriptive only.

## Outcome and reproducibility

Only `VERIFIED` labels from `deterministic_forward_outcome_rule_v1` enter
predictive metrics. `REQUIRES_HUMAN_REVIEW` and `INSUFFICIENT_DATA` are never
coerced and remain in attrition analysis.

Deterministic stages are independently rerun and compared using canonical
byte-identical outputs. Agent replay uses frozen requests and responses;
stochastic stability is reported separately. README claims are rendered only
from `research/e4/public/readme_summary.json` after `EVALUATED` and
`REPRODUCED`.

E4 can evaluate structured financial ranking, temporal structured signal,
local Agent reasoning, and a deterministic–Agent hybrid. It does not validate
calibrated default probability, universal bankruptcy prediction,
production/regulatory use, a full narrative/document Agent, MD&A or Risk
Factor grounding, or full FinRisk Agent external validation.
