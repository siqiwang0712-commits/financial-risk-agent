# E5 Blinded Outcome Adjudication Protocol

Status: **PROSPECTIVE — FROZEN BEFORE OUTCOME ACCESS**

Purpose: raise high-quality outcome coverage above E4's 33.7% deterministic rate
**without** letting any knowledge of system performance leak into the labels.

---

## 1. The problem being fixed

E4's endpoint verified only 674 of 2,000 observations. E4's own post-hoc audit found that
availability was *predictable from prediction-time characteristics alone*: a
prediction-time-only, five-fold cross-fitted propensity model reached AUROC 0.740, several
standardised mean differences exceeded 0.4, and the untruncated inverse-propensity maximum
weight reached 24.63 with an effective sample size of only 247.2.

Consequently E4's 0.708 AUROC describes the deterministically verifiable subset, not the
2,000-company population. Weighting cannot repair this, because missingness is not
demonstrably at random. The fix is not better statistics on the same labels — it is
**more and better labels**.

---

## 2. Two-tier outcome

| Tier | Status | Decision maker |
|---|---|---|
| 1 | `VERIFIED` | `deterministic_forward_outcome_rule_v1` (unchanged from E4) |
| 2 | `REQUIRES_HUMAN_REVIEW` → `VERIFIED` or `NOT_DETERIORATED` | blinded reviewers |
| — | `INSUFFICIENT_DATA` | never converted; reported in attrition only |

A Tier-2 case becomes evaluable only through an explicit reviewer verdict. No case is
coerced into a binary label by rule.

---

## 3. Reviewer panel

- Reviewer A and Reviewer B independently label every Tier-2 case.
- Reviewer C adjudicates only where A and B disagree.
- Reviewers are identified in artifacts by role only.
- A reviewer must not have contributed to the prediction pipeline and must not have seen
  any system output.

---

## 4. Blinding (absolute)

Review packets contain **only** the future financial evidence required to construct the
endpoint. Reviewers must not see:

- B0, B1, B2, B3, B6, A0, A1, A2, A3 or Hybrid scores
- any prediction, any thresholded decision, any rank
- the model identity, prompt, or representation used
- the sector-stratified selection order
- the other reviewer's verdict before recording their own

Each reviewer records a verdict, a confidence, and a free-text rationale before any
disagreement information is revealed. Rationales are stored so that a third party can
audit the reasoning.

*Why this matters:* if a reviewer can infer the system's score, the label becomes partly a
function of the prediction, and the confirmatory test measures agreement with the reviewer
rather than predictive validity. That failure mode is invisible in the final numbers.

---

## 5. Disagreement resolution

1. A and B label independently.
2. Disagreements go to C, blind to A's and B's verdicts and blind to all scores.
3. C's verdict is final and is marked `ADJUDICATED`.
4. C's verdicts are reported separately from unanimous verdicts so that their influence on
   the result is visible.

---

## 6. Required reporting

- raw agreement (A vs B)
- Cohen's κ with its CI
- disagreement rate
- adjudication rate (share of Tier-2 cases reaching C)
- per-reviewer positive rate
- Tier-1 coverage, Tier-2 coverage, final evaluable coverage
- prediction-time covariate balance across `VERIFIED` / `NOT_DETERIORATED` /
  `INSUFFICIENT_DATA` (size, missingness, fact count, filing timing, B0, B6) with
  standardised mean differences
- a verification-propensity model refit on the E5 cohort, reported as a **diagnostic**
  only

---

## 7. Prespecified gates

Frozen before outcome access:

- minimum evaluable coverage (as a fraction of the cohort)
- minimum paired event count (see the study protocol's unlock gate)
- maximum acceptable standardised mean difference for the selection diagnostics

If a gate is missed, the primary analysis is reported as
`EXPLORATORY_INSUFFICIENT_POWER`. It is **not** rescued by re-adjudication, by adding
reviewers after seeing results, or by reweighting. Reweighting may be reported as a
prespecified sensitivity analysis, but it never replaces missing labels.

---

## 8. What this protocol does not claim

It does not make the endpoint a validated clinical or regulatory outcome. It does not
establish that adjudicated labels are unbiased in general — only that they were produced
without access to system predictions. Any residual reviewer bias is a limitation to be
stated, not a property to be assumed away.
