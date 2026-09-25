# E5 — Confirmatory External Validation of Structured Agent Reasoning

Status: **PROSPECTIVE PROTOCOL — READY TO FREEZE — NO COHORT, NO PREDICTIONS, NO OUTCOMES**

Supersedes `research/e5/STUDY_PROTOCOL_DRAFT.md` (retained as history). This document is
the freeze candidate. Nothing here may be edited after the freeze commit; amendments must
be recorded as a new, separately committed amendment with its own hash.

---

## 0. Why E5 exists

E4 established exactly one claim: the temporal structured signal B6 improved ranking over
the ratios-only baseline B0 on E4's deterministically verified subset (paired ΔAUROC
`+0.0303`, 95% CI `+0.0136` to `+0.0481`). Everything else in E4 — the Local Agent, the
fixed Hybrid, population-wide performance, calibration — came back
`NOT_ESTABLISHED` or `EXPLORATORY_INSUFFICIENT_POWER`.

E5 answers the one question E4 could not:

> **Does structured Agent reasoning provide incremental predictive value beyond a strong
> deterministic temporal financial-risk baseline?**

E5 is *not* a rerun of E4 at larger N. Three structural defects in E4 are fixed by design:

| E4 defect | E5 fix | Section |
|---|---|---|
| Label-permutation test does not test `H0: AUROC(A) = AUROC(B)` | Prespecified paired DeLong as the primary test; permutation design constrained | §6 |
| Deterministic-only outcome coverage 33.7% | Blinded two-tier adjudication layer | §8 |
| Protocol, implementation and results first published in one commit | Staged, separately committed, hash-anchored governance | §11 |

---

## 1. Isolation and novelty

E5 is confirmatory only if its cohort and outcomes were unavailable when the protocol,
cohort, packets and predictions were frozen.

1. The feature period must be **later than E4's**. E4 used original FY2024 10-K filings
   filed 2024-07-01 to 2025-06-30. E5 uses original **FY2026** 10-K filings filed in the
   corresponding later window, and the outcome window must lie entirely after the
   prediction freeze.
2. Companies must be disjoint from every prior cohort: E1, E2, E3,
   `research/results/public_v1`, the historical development corpus, the E4 cohort, and the
   prior 270-CIK external-validation cohort.
3. **Unused E4 companies are not eligible.** E4's outcomes, design feedback and post-hoc
   analyses are already public; reusing an unused E4 company would be retrospective, not
   prospective.
4. Outcome storage is not mounted into any container that can produce a prediction. The
   prediction freeze is content-addressed and committed before the outcome mount exists.

**Blocking prerequisite.** E4's `research/e4/_cache/previous_270.json` is unpublished
(only its SHA-256 is pinned). Until the 270-CIK list is published, E5 cannot prove
company-disjointness against that cohort. Publishing it is a precondition for the E5
cohort freeze, not an optional nicety.

---

## 2. Estimand

The primary estimand is the **paired difference in AUROC on the common evaluable cohort**:

```
Δ_XY = AUROC(X) − AUROC(Y)
```

evaluated on the same companies, using each company's single forward
financial-deterioration outcome. All scores remain `UNCALIBRATED` heuristic indices.
E5 does not estimate a probability of default, a bankruptcy probability, or a credit loss.

Secondary estimands: paired ΔPR-AUC with event prevalence reported beside it, balanced
accuracy, recall, specificity, precision, F1, false-negative rate, coverage, and a
descriptive Brier score.

---

## 3. Confirmatory systems

| ID | System | Role |
|---|---|---|
| B0 | committed `ratio_risk_score` | locked reference |
| B6 | committed `temporal_risk_score` | locked reference; the baseline the Agent must beat |
| A2 | strong Agent, representation A2 | primary Agent arm |
| H  | fixed Hybrid | primary hybrid arm |

B1 (logistic), B2 (rule engine), B3 (Altman/Beneish/Piotroski/Ohlson), A0 and A1 are
**secondary / ablation / diagnostic only** and are excluded from the primary inference
family.

**Representation choice.** Exactly one Agent representation is nominated as primary; see
`AGENT_REPRESENTATIONS.md` for the exact field list of each representation as the frozen
`packet()` builds it. The default nomination is **A2** (raw facts + engineered metrics +
traditional-model outputs). A new `A3 = A2 + explicit temporal trajectory` may be nominated
*instead* of A2 only if its definition, extraction code and prompt are frozen in the
protocol commit, before any cohort or outcome access. A2 and A3 must not both be primary.

**Confound to confront, not inherit.** `AGENT_REPRESENTATIONS.md` §2 shows, with code
citations, that A1 and A2 packets contain **every input that B0 and B6 use**: the baselines
and the Agent read the same `row["metrics"]` dict. Two things follow and are binding on E5:

- H1/H2 compare **aggregation strategies over an identical feature set**, not information
  access. The Agent is given B6's inputs, so a high H1 result may be successful imitation of
  B6 rather than evidence of reasoning. E4's protocol claim that A2 carries "no B0/B2/B6/
  Hybrid final score" is true about the *score* and misleading about the *information*.
- The **aggregation-equivalence diagnostic** in §3 of that document is prespecified and
  reported for every Agent arm. If the Agent's advantage disappears once `(B0, B6)` are
  partialled out, the finding is that the Agent re-weighted the baselines, and it must be
  reported in those words.

A3's rationale is therefore **horizon**, not extra deltas: A2 already contains every
year-over-year delta B6 uses. A3 must expose a multi-year series from the same accession,
which no baseline sees. If the multi-period extraction is not implemented and frozen before
the cohort is enumerated, A3 is ineligible and A2 is primary.

**Hybrid.** The primary hybrid is the transparent fixed fusion
`H = 0.5 × B6 + 0.5 × A2`, carried over unchanged from E4 so that the E4→E5 comparison is
like-for-like. A learned fusion is permitted only if its coefficients are fitted on a
development set that is disjoint from the E5 cohort and from every E4 company, and frozen
before outcome access; the fitted coefficients become part of the protocol hash.

---

## 4. Cohort

- Candidate set: original FY2026 Form 10-K filings, non-financial SIC, valid CIK and
  accession, at least one computable B0 component, at least one same-filing temporal
  component.
- Cohort construction algorithm and salt are frozen in this protocol **before** the
  candidate set is enumerated. The E4 algorithm (proportional SIC strata, largest
  remainder, ascending SHA-256 within stratum) may be reused with a **new salt**
  `finrisk-e5-cohort-v1:`.
- The Agent cohort is not capped at E4's 50. Its size comes from §7, not from a runtime
  budget.

---

## 5. Agent runtime and inference policy

1. **One company per semantic LLM request.** Multiple companies must never share a model
   context. Concurrency is permitted at the transport and scheduling layer only.
   *Justification:* E4's batch-vs-single comparison showed a mean absolute score
   difference of 0.101 and a rank correlation of only ~0.313. A ranking study cannot
   tolerate cross-company context contamination.
2. The model is selected by §9, before outcome access, and frozen with its exact identity,
   weights digest, tokenizer, quantization, context length, runtime, temperature, seed,
   thread count, retry policy and batch policy.
3. The Agent sees only anonymised packets. No web, no tools, no shell, no repository, no
   future data, no other model's output, no deterministic final score (B0/B2/B6/Hybrid).
4. Retry and recovery are deterministic: one unchanged retry, then deterministic
   left/right bisection down to a single permanent failure, recorded with an error code
   and a hash of the masked invalid response.

---

## 6. Hypothesis hierarchy and multiplicity

At most three primary comparisons. Everything else is secondary.

| ID | Comparison | Question |
|---|---|---|
| **H1** | A2 vs B6 | Given **the same feature set as B6**, does a strong Agent produce a better *ranking* than B6's fixed `0.75/0.25` blend with hard thresholds? (An aggregation question — see §3.) |
| **H2** | H vs B6 | Does the Agent add **incremental** value on top of B6? |
| **H3** | H vs A2 | Are the deterministic temporal signal and Agent reasoning **complementary**? |

H2 is the study's primary question; H1 and H3 decompose it.

**Primary test.** Paired **DeLong** (DeLong, DeLong & Clarke-Pearson 1988) on ΔAUROC,
computed on the common evaluable cohort.

*Why DeLong and not E4's permutation test.* The E4-S audit established that E4's
label-shuffling permutation samples the null of *no signal in either score*, not the null
of equal AUROCs. Its p-value therefore cannot be attached to `H0: AUROC(A) = AUROC(B)`.
DeLong is the standard asymptotically valid test for two correlated ROC AUCs and is the
prespecified primary test for E5.

**Primary interval.** Company-cluster **BCa** bootstrap, 20,000 replicates, with the
delete-one-cluster jackknife acceleration. The cluster is the resampling unit because
there is one observation per company.

**Multiplicity.** **Holm step-down over {H1, H2, H3}**, family-wise α = 0.05, applied to
the three DeLong p-values. The procedure is frozen here, before any outcome exists. No
other family is adjusted; secondary comparisons are reported as unadjusted and explicitly
labelled descriptive.

**Decision rule.** A primary hypothesis is `ESTABLISHED_E5` if and only if all three hold:

1. Holm-adjusted p < 0.05;
2. the paired BCa 95% CI for ΔAUROC lies entirely above 0;
3. the frozen minimum event gate (§7) is met.

Otherwise the status is `NOT_ESTABLISHED` — never "trending", never "underpowered but
positive".

**Prespecified robustness (non-primary).** The within-observation score-swap
randomization test; the label-permutation test in its original form, reported **only** as
a test of its own null; and threshold sensitivity over 0.2–0.8 as a sensitivity analysis,
never as retuning.

---

## 7. Sample size and power

Determined by simulation, not by a fixed N. `power_analysis.py` in this directory
generates `power_analysis.json`.

Planning inputs, all of which are E4 *operational* rates or a-priori design choices:

| Input | Value | Source |
|---|---|---|
| verified rate | 0.60 | design assumption for the E5 adjudication layer, vs E4's 0.337 deterministic-only |
| event prevalence | 0.3487 | E4 operational rate |
| schema success | 0.99 | E5 qualification gate (§9) |
| B6 AUROC | 0.7080 | E4 observed |
| α | 0.05 | nominal |
| target power | 0.80 and 0.90 | design choice |

The **minimum meaningful ΔAUROC** is a design choice and must be declared in the freeze
commit. The power analysis reports the required cohort for ΔAUROC ∈ {0.02, 0.03, 0.04,
0.05, 0.06, 0.08} and score correlation ∈ {0.85, 0.90, 0.95}, so the freeze can pick a
defensible pair rather than the most flattering one.

**Unlock gate.** Outcomes may not be unlocked unless the frozen cohort is projected to
deliver at least **100 paired positive events** after endpoint and schema attrition at the
frozen minimum meaningful effect. If the projection falls short, the correct action is to
enlarge the cohort or declare E5 exploratory *before* outcome access — never to lower the
gate afterwards.

**Attrition sensitivity** is reported for verified rate ∈ {0.337, 0.45, 0.55, 0.65, 0.75}
× schema success ∈ {0.90, 0.95, 0.99}.

---

## 8. Outcome adjudication (the largest E5 design upgrade)

E4's deterministic endpoint verified only 674/2000 observations. E5 adds a blinded
adjudication layer to raise high-quality coverage **without** prediction-informed
labelling.

**Tier 1 — `VERIFIED` (deterministic).** Unchanged from E4:
`deterministic_forward_outcome_rule_v1` applied to the future archives.

**Tier 2 — `REQUIRES_HUMAN_REVIEW` (adjudicated).** Two blinded reviewers independently
decide whether the constructed endpoint is met, using **only** the future financial
evidence needed to construct that endpoint.

**Blinding is absolute.** Reviewers must not see B0, B6, A0, A1, A2, H, any score, any
prediction, any threshold, the model identity, or each other's verdict before recording
their own. Review packets are stripped to the endpoint-construction evidence. A reviewer
who can infer the system's score can bias the label, which would silently convert a
confirmatory test into a self-fulfilling one.

**Disagreement resolution.** Reviewer A and Reviewer B each record a verdict. If they
disagree, Reviewer C adjudicates blind to A and B's verdicts, and blind to all scores.
Reviewer C's verdict is final and is recorded as an adjudicated label.

**Required reporting.** Raw agreement, Cohen's κ, disagreement rate, adjudication rate,
per-reviewer positive rate, and final evaluable coverage. Reviewers are identified only by
role, never by name.

**Never coercive.** `INSUFFICIENT_DATA` records are never converted to labels. Attrition
is reported as an outcome of the study, not as a preprocessing step.

**Prespecified coverage floor.** The study prespecifies a minimum evaluable coverage and a
minimum paired event count before outcome access. If adjudication misses the floor, the
primary analysis is reported as `EXPLORATORY_INSUFFICIENT_POWER` — it is not rescued by
re-adjudication.

---

## 9. Agent qualification (outcome-blind)

A 0.5B model is not an acceptable primary Agent for E5. Qualification happens in a
separate, outcome-blind stage; see `AGENT_QUALIFICATION_PROTOCOL.md`.

Headline gates:

- ≥ 99% schema-valid outputs on the qualification set;
- exact input/output case-ID equality;
- no missing outputs;
- valid `risk_score` in [0, 1];
- deterministic retry and bisect recovery demonstrated;
- batch-size sensitivity measured at sizes 1, small, target with frozen tolerances;
- reproducibility across repeated runs;
- latency and token cost recorded;
- a failure taxonomy with deterministic error codes.

The qualification set is 100–200 packets that are **historical, synthetic or otherwise
non-E5 and outcome-blind**. Model selection uses a frozen lexicographic rule over
reliability, context fit, reproducibility, hardware feasibility and latency — **never E5
outcome performance**.

---

## 10. Calibration

Unless there are three genuinely distinct splits — development, calibration, and final
validation — every score remains `UNCALIBRATED`.

If a calibration track is attempted, its method and bins are fitted on the calibration
split only, and the final validation split reports calibration intercept, calibration
slope, Brier score, ECE, calibration plots and discrimination **without refitting**. A
`[0, 1]` risk score is never to be read as a probability.

---

## 11. Governance: staged, publicly verifiable freeze

E4's protocol, implementation and results first appeared in public history in a single
commit (`96e60ae`, "research: add E4 comparative validation"), which is why E4 can claim
only that it is *internally frozen and auditable* and not that it was publicly
preregistered. E5 must not repeat this.

Required sequence, each step its own commit (or annotated tag), each commit carrying a
content hash, a manifest, a timestamp and a source commit:

```
1. protocol commit            — this document + config + power analysis + frozen hashes
2. agent-qualification commit — qualification packets, results, chosen model + digest
3. cohort-freeze commit       — candidate enumeration, algorithm, salt, final cohort
4. feature-freeze commit      — feature hash, no outcomes mounted
5. prediction-freeze commit   — content-addressed prediction hash, no outcomes mounted
6. outcome-unlock commit      — outcome archives mounted, label hash recorded
7. adjudication commit        — adjudicated labels, agreement statistics
8. evaluation commit          — primary results, all prespecified secondary analyses
9. results commit             — public claims rendered from the canonical summary only
```

Rules:

- No commit may be amended, rebased or force-pushed after it is pushed.
- Step *n+1* must not exist at the time step *n* is pushed.
- The protocol hash must be verifiable against the protocol commit's tree.
- A failed or negative result is published exactly as computed. The pipeline is never
  re-run with a changed prompt, threshold, weight, sample, endpoint or model to improve a
  headline number.

`GOVERNANCE_WORKFLOW.md` contains the exact commands and the manifest schema.

---

## 12. What E5 will and will not establish

**Will establish (if the gates pass):** whether a strong structured Agent, and a fixed
deterministic-Agent hybrid, provide incremental ranking value beyond B6, on a new,
company-disjoint, prospectively frozen cohort with blinded adjudicated outcomes.

**Will not establish:** calibrated default probability; universal bankruptcy prediction;
production or regulatory fitness; full-document/MD&A reasoning (that is E5-Narrative);
any named commercial model's capability; or any claim about the E4 cohort.

`E5-Narrative` is a separate study with its own protocol, ground truth and metrics
(claim extraction, evidence grounding, citation correctness, contradiction detection,
temporal change detection, unsupported-claim rate, abstention quality). It must not be
merged into structured E5.

---

## 13. Evidence statuses used by E5

| Status | Meaning |
|---|---|
| `ESTABLISHED_E5` | Passed the prespecified inference and claim gate. |
| `NOT_ESTABLISHED` | The gate was not passed. This is a result, not a failure. |
| `EXPLORATORY_INSUFFICIENT_POWER` | The frozen power or event gate was not met. |
| `NOT_TESTED` | No qualifying experiment has been run. |
| `UNCALIBRATED` | No calibration track exists; the score is not a probability. |

---

## 14. Freeze checklist

Before the protocol commit is pushed:

- [ ] Minimum meaningful ΔAUROC declared.
- [ ] Primary representation nominated (A2 **or** A3, not both).
- [ ] Hybrid fusion rule and any fitted coefficients frozen.
- [ ] Multiplicity procedure stated (Holm over H1/H2/H3).
- [ ] Primary test stated (paired DeLong) and the permutation design constrained.
- [ ] Power analysis regenerated with the declared ΔAUROC; unlock gate recorded.
- [ ] 270-CIK exclusion list published, or the cohort-disjointness claim explicitly
      marked `NOT_ESTABLISHED`.
- [ ] Agent qualification protocol and lexicographic selection rule frozen.
- [ ] Blinded adjudication protocol, reviewer count and disagreement rule frozen.
- [ ] Environment variables required to read the archives recorded (see §15).
- [ ] Coverage floor and minimum paired event count frozen.

## 15. Environment recording requirement

E4's outcome construction requires `FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES` to be raised
above its 256 MB default: the SEC FSDS `num.txt` members are 500–600 MB, and the frozen
v0.3.4 guard rejects them at the default. This override is recorded in neither E4's
`experiment_config.json` nor its post-hoc `environment_manifest.json`, so E4's outcome
stage is not reproducible from its own documentation.

E5 must therefore freeze **every environment variable that can change a result**, not only
package versions. `experiment_config.json` in this directory carries an explicit
`environment_variables` block for that purpose.
