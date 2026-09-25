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

## E4-S statistical audit

E4-S re-tests E4's primary inference and re-executes the frozen pipeline from
public inputs. It touches nothing under `research/e4/`, and a SHA-256 manifest of
every published E4 artifact plus
`tests/test_e4_statistical_audit.py::test_frozen_e4_artifacts_are_byte_identical`
prove it.

E4's per-observation rows were never published, so the audit re-ran the frozen
v0.3.4 pipeline with an empty 270-CIK exclusion (a documented deviation) and
publishes its own cohort, predictions and paired rows under
`research/e4_statistical_audit/replication/`. That cohort is **675 observations /
235 events**, **~94% overlapping** with E4's 674 — a near-reproduction, not an
independent sample.

| Method | Null it actually tests | ΔAUROC | 95% interval | p |
|---|---|---:|---|---:|
| E4 frozen label permutation (2,000) | `H0_independence` | +0.0303 | — | 0.0004998 (floor) |
| paired DeLong (the prespecified target) | `H0_equality` | +0.0264 | [+0.0101, +0.0426] | 0.001440 |
| cluster BCa bootstrap (20,000) | `H0_equality` | +0.0264 | [+0.0111, +0.0438] | — |
| score-swap randomization (20,000) | `H0_exch` | +0.0264 | null [−0.0185, +0.0184] | 0.004500 |

Verdict `CONSISTENT_SUPPORT`: every test that targets the equality hypothesis
rejects in the same direction with the same point estimate.

Two findings sit beside that verdict and must be reported with it:

- **E4's p-value is not a test of the hypothesis E4 states.** It shuffles labels
  while holding each `(B0, B6)` pair fixed, so its reference distribution is the
  distribution of ΔAUROC under `H0_independence` — the outcome is independent of
  *both* scores. Rejecting that establishes that at least one score carries
  signal; it does not establish that B6 carries more than B0. The published value
  is also exactly `1/2001`, the attainable floor at 2,000 permutations.
- **At E4's design point the procedure is nonetheless close to nominal.** A
  200-replicate simulation gives size 0.025 against α = 0.05 and power 0.930
  against DeLong's 0.935. E4's numerical conclusion is therefore unaffected; the
  defect is one of logic and interpretability, not of measured error rate here.

The audit also confirms E4's published calibration diagnostics to within about
0.006 and recommends citing the score-support facts — 42% of B0's mass sits at
exactly 0 where the event rate is 26% — rather than the ill-conditioned
calibration slope.

Canonical detail: [E4-S audit report](e4_statistical_audit/AUDIT_REPORT.md) and
[method cross-check](e4_statistical_audit/inference_crosscheck.json).

## E4-R automated robustness and competitive baselines

E4-R is a `POST_HOC_AUTOMATED_ROBUSTNESS` study run on E4-S's published
replication packet. It prespecifies its own configuration
(`experiment_config.json`, then `extension_config.json`), aborts if either hash
moves, and evaluates robustness and competitive baselines only.

On the same 675 / 235 cohort, eleven nested-CV baselines (5×5 company-level
stratified folds, preprocessing fitted inside the fold):

| Scorer | Out-of-fold AUROC | PR-AUC |
|---|---:|---:|
| B0 (frozen heuristic) | 0.679 | 0.541 |
| B6 (frozen heuristic) | 0.705 | 0.581 |
| Logistic, static only (`logistic_F0`) | 0.827 | 0.769 |
| Logistic, static + temporal (prespecified linear challenger) | 0.819 | 0.754 |
| Gradient boosting, temporal only (`hist_gb_F1`) | 0.863 | 0.776 |
| Gradient boosting, static + temporal (prespecified nonlinear challenger) | 0.885 | 0.839 |

P1 `B6 − B0` reproduces: ΔAUROC **+0.0264**, paired DeLong p = 0.00144,
Holm-adjusted p = 0.00144, 20,000-replicate BCa **[+0.0109, +0.0434]**.
P2 `logistic_F2 − B6` is **+0.1136** (Holm p = 1.2e-05) and P3
`hist_gb_F2 − B6` is **+0.1797** (Holm p underflows double precision at
z = 8.39).

Three pre-registered interpretation cases fire:

- **Case B** — B6's hand-designed aggregation is not competitive with a learned
  nonlinear tabular baseline.
- **Case D** — E4's gain depends materially on the temporal block. This is a
  *structural* result: `B6_no_temporal = 0.75 × B0` is a strictly increasing map
  of B0, so its AUROC equals B0's exactly and all B6 − B0 ranking separation is
  mechanically introduced through the temporal component. It is not a causal
  finding, and the gain is not concentrated in one term — removing
  `cash_growth` slightly *improves* AUROC.
- **Case F** — the aggregate improvement is not uniformly robust across the
  population, though only as a marker: `Transportation_Utilities`'s −0.005 point
  estimate has an interval containing zero.

The post-hoc hardening pass (`extension_config.json`,
[EXTENSION_PROTOCOL.md](e4r_automated_robustness/EXTENSION_PROTOCOL.md)) closes
three gaps and cannot upgrade any statement:

- **A material share of the learned-model advantage is reporting structure.**
  Removing the imputer's missing-value indicators costs the logistic −0.160
  AUROC (95% CI [−0.209, −0.110]) and the boosting model −0.026
  ([−0.040, −0.014]). A model given *only* the nine presence/absence flags — no
  financial value at all — reaches 0.835 (boosting) and 0.829 (logistic), i.e.
  +0.13 above B6. This is explicitly **not** called leakage: nothing shows an
  indicator carries outcome-side information, and the timestamp checks pass.
  Strict complete-case leaves 154 observations and 10 events and is reported as
  `NOT_ESTIMABLE` rather than estimated.
- **Temporal features add little once a strong static nonlinear learner is
  used.** `hist_gb_F0` (static only) reaches 0.880 against `hist_gb_F2`'s 0.885:
  Δ **+0.0056**, paired DeLong p = 0.39, BCa [−0.007, +0.019]. The superseded
  `F1 → F2` comparison could not answer this because `hist_gb_F0` did not exist.
- **The temporal-shuffle control is genuinely paired** (one shared
  configuration; the original arm's folds asserted equal to the frozen run's).
  Shuffling costs the boosting model a median +0.012 AUROC with 0 of 100
  replicates reaching the original; the logistic moves +0.001 with
  P(drop>0) = 0.61. The earlier 0.8741-versus-0.8851 discrepancy is explained as
  an inner-grid difference and retained as an audit note rather than deleted.
- **Sector heterogeneity is not established.** No gated sector has an
  interval-supported negative effect, and a 2,000-replicate permutation test does
  not reject a common effect (p = 0.25, I² = 0.10).
- **Interval honesty.** The reported DeLong and bootstrap intervals condition on
  the realized out-of-fold predictions and do not integrate training-procedure
  uncertainty; repeated 5×5 nested CV measures that omitted component at
  sd ≈ 0.004 (boosting) and 0.006 (logistic).

Canonical detail: [E4-R final report](e4r_automated_robustness/FINAL_REPORT.md),
[study protocol](e4r_automated_robustness/STUDY_PROTOCOL.md) and
[interpretation policy](e4r_automated_robustness/INTERPRETATION_POLICY.md).

## Current conclusion

E4 established a limited improvement from temporal structured signal over the
ratios-only baseline on its deterministically verified subset, and that direction
survives an independent, correctly specified inference (E4-S). E4's *stated*
justification does not: the published P1 p-value tests a different null and sits
at its attainable floor.

E4-R then shows what that improvement is worth against conventional tabular
learning: little. B6 is not competitive with a strong nested-CV baseline on the
same features, a material share of the learned advantage is reporting structure
rather than financial-value signal, and temporal features add little on top of a
strong static nonlinear learner.

Agent and Hybrid incremental value, population-wide performance, probability
calibration, full-document reasoning and production/regulatory fitness remain
unestablished. **E5 must use a genuinely new time window, and its primary
benchmark must be a strong tabular baseline on the same feature set rather than
B0 — with a missingness-only arm alongside it, because a model that never sees a
financial value already approaches B6 here.**
