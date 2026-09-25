# FinRisk v0.3.4 / E4 Results

This document is the compact result surface for the current release. Canonical
values remain in the linked E4 reports and JSON files. Historical pilot and
v0.3.1 outputs are retained for audit but are not used as current evidence.

## Study design and sample flow

E4 locked FinRisk v0.3.4 at commit
`4273b070678240fe7cbdf01a17527afcc71c500e`. It selected 2,000
company-disjoint FY2024 10-K filers before future-outcome access. The frozen
endpoint produced:

| Outcome status | Count |
|---|---:|
| `VERIFIED` | 674 |
| Events within `VERIFIED` | 235 |
| `REQUIRES_HUMAN_REVIEW` | 571 |
| `INSUFFICIENT_DATA` | 755 |

Verified endpoint coverage was 33.7%. Performance estimates therefore apply
to the deterministically verifiable subset.

## E4-A primary deterministic result

| System | Verified N | Events | AUROC (95% CI) | PR-AUC |
|---|---:|---:|---:|---:|
| B0 Ratios Only | 674 | 235 | 0.678 (0.633–0.721) | 0.541 |
| B6 Temporal Risk | 674 | 235 | 0.708 (0.663–0.750) | 0.584 |

P1, B6 minus B0, produced paired ΔAUROC `+0.030` with 95% CI `+0.014`
to `+0.048` and Holm-adjusted `p=0.0015`. This passed the prespecified
positive-improvement gate and is `ESTABLISHED_E4` on the verified subset.

## E4-B paired structured comparison

All systems below use the same 18 verified E4-B observations. Agent failures
remain in coverage rather than being imputed.

| System | N / events | AUROC | PR-AUC | Recall | Specificity | Coverage |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 18 / 5 | 0.531 | 0.500 | 0.400 | 0.923 | 100.0% |
| B2 | 18 / 5 | 0.646 | 0.389 | 0.800 | 0.385 | 100.0% |
| B3 | 18 / 5 | 0.500 | 0.333 | 1.000 | 0.231 | 100.0% |
| B6 | 18 / 5 | 0.608 | 0.544 | 0.200 | 1.000 | 100.0% |
| A0 | 18 / 5 | 0.692 | 0.459 | 1.000 | 0.000 | 100.0% |
| A1 | 18 / 5 | 0.477 | 0.299 | 1.000 | 0.000 | 100.0% |
| A2 | 16 / 5 | 0.436 | 0.343 | 1.000 | 0.000 | 88.9% |
| H0 | 16 / 5 | 0.582 | 0.604 | 0.600 | 0.364 | 88.9% |

The Local Agent was Qwen2.5 0.5B Instruct Q4_K_M through Ollama 0.12.3
on CPU. Five of 150 official Agent records failed permanently. P2 H0−B0
(`+0.055`, 95% CI `−0.071` to `+0.191`) and P3 H0−A2 (`+0.145`, 95% CI
`−0.286` to `+0.527`) had only five paired events. Neither improvement was
established.

Canonical detail: [E4 validation report](e4/public/VALIDATION_REPORT.md),
[E4 conclusion](e4/public/CONCLUSION.md) and
[machine-readable summary](e4/public/readme_summary.json).

## Robustness and integrity

- All eight SEC archives passed SHA-256, CRC, required-member, size and
  integrity checks.
- Feature and outcome mounts were separated through prediction freeze.
- Deterministic stages reproduced byte-identically; frozen Agent responses
  replayed to the same predictions.
- Verification propensity AUROC was 0.740, showing that verified availability
  was associated with prediction-time characteristics. Weighting is
  sensitivity analysis only because MAR cannot be established.
- Original batch versus single-case Agent scores differed by 0.101 on average.
  Binary agreement was 96.6%, but rank correlation was only about 0.313.
- SEC–Zenodo processing/source concordance covered 17,757 values from 1,648
  companies; 90.9% agreed within 5%. This is concordance, not extraction
  accuracy.
- Every system remains `UNCALIBRATED`.

Canonical detail: [post-completion audit](e4_posthoc/AUDIT_REPORT.md) and
[post-hoc conclusion](e4_posthoc/POSTHOC_CONCLUSION.md).

## Post-hoc Codex sub-Agent comparator

The comparator uses the project-internal display name `ChatGPT5.6 Sol`. It was
executed by Codex sub-Agents over the same 50 frozen anonymous E4-B A0/A1/A2
packets. The name is not an official OpenAI or ChatGPT model identity, and the
platform did not expose the exact underlying model ID or complete runtime
attestation.

| Comparator | Verified N / events | AUROC | PR-AUC |
|---|---:|---:|---:|
| A0 | 18 / 5 | 0.815 | 0.777 |
| A1 | 18 / 5 | 0.800 | 0.711 |
| A2 | 18 / 5 | 0.738 | 0.652 |
| Fixed H0: 0.5 × B6 + 0.5 × A2 | 18 / 5 | 0.708 | 0.583 |

All 150 judgments passed public output-schema, ID, score and threshold checks;
their input hashes were also verified against the local frozen packet
manifest. The experiment was commissioned after E4 outcomes were known, only
five verified events were available, and its exact inference runtime is not
independently reproducible. These results are `POST_HOC`, `UNCALIBRATED` and
insufficiently powered. They do not replace E4 or establish named-model
superiority.

Canonical detail: [comparator methodology](e4_posthoc/model_capacity/sol_codex_agent/METHODOLOGY.md)
and [results JSON](e4_posthoc/model_capacity/sol_codex_agent/results.json).

## Current conclusion

E4 established a limited improvement from temporal structured signal over the
ratios-only baseline on its deterministically verified subset. Agent and
Hybrid incremental value, population-wide performance, probability
calibration, full-document reasoning and production/regulatory fitness remain
unestablished. E5 must use a genuinely new time window to test those questions
confirmatorily.
