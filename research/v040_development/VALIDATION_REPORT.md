# v0.4 Internal Development Validation

Status: **RETROSPECTIVE · POST_HOC · DEVELOPMENT · NOT_CONFIRMATORY**

This report records software-mechanism validation for the v0.4 release candidate. It is
not an outcome study, calibration study, prospective E5 result, or external validation.
No new cohort, future outcome, predictive leaderboard, or headline AUROC was produced.

## Scope and result

Internal development validation is **COMPLETE for the v0.4.0 software release scope**:

- prediction components produce proposals; only a policy-bound, hash-verified
  `AssuranceResult` authorizes the final decision;
- missing or mutated assurance state fails closed;
- removing evidence cannot improve evidence assurance;
- frozen-graph fragility is deterministic and makes no LLM/provider call;
- non-material and critical evidence removals produce the expected stable/sensitive/
  fragile behavior and decision-impact diagnostics;
- Decision-Sufficient Evidence exercises `EXACT` and `GREEDY_APPROXIMATION`, with
  approximate output always marked `exact: false`;
- `IN_REFERENCE`, `WARNING`, `OUTSIDE_REFERENCE`, and `UNKNOWN` are exercised, and
  worsening validity never increases automation eligibility;
- reporting observability remains separate from financial severity;
- Decision Certificates build, serialize, deserialize, verify, replay, and reject
  proposal/final/policy/evidence/validity/automation mutations;
- a synthetic end-to-end path runs input → proposal → Assurance → final decision →
  certificate → verify → replay;
- PostgreSQL migration, API serialization, persistence, API restart, certificate
  retrieval/deduplication, and post-restart replay pass in both development and
  release-oriented Compose paths.

The full backend suite passed on Python 3.11.16 and 3.12.14 with 643 passed, 17 skipped,
and 90.90% coverage on each interpreter. The skipped tests are environment-gated; the 12
PostgreSQL tests were then run against PostgreSQL 17 and passed. Frontend tests, lint,
TypeScript checking, and the production build passed.

## Development reference

[`development_reference.json`](development_reference.json) is explicitly scoped
`DEVELOPMENT_REFERENCE_ONLY`. It is deterministically derived from one synthetic fixture,
records its source identity/commit/schema/statistics/method/hash/limitations, and exists
only to reproduce the four distribution-validity states in tests and the demo.

It is not representative, calibrated, empirical, externally validated, or eligible to
support real-world automation. Unknown and unsupported inputs continue to fail closed.

## Research integrity

- Frozen E4 public artifacts: PASS.
- E4-S quick independent verifier: 44/44 PASS.
- E4-R verifier: 136/136 PASS.
- E5 freeze-chain status: `NOT_FROZEN`, with all nine stages absent.

The E4-R verifier formerly failed its temporal-ablation reconstruction on Python 3.13+
because a helper selected the first numeric code constant rather than the constant loaded
for the comparison. The exact failure reproduced on untouched commit
`69cafe6a8afbb35aceec27a8e27660419d401b57` (467/675 mismatches; maximum absolute error
0.25). The verifier now reads the `LOAD_CONST` operand preceding `COMPARE_OP`. Frozen
predictions, results, manifests, and conclusions were not modified.

## Maturity boundary

The release remains:

```text
ASSURANCE POLICY: HEURISTIC_POLICY / UNCALIBRATED
INTERNAL DEVELOPMENT VALIDATION: COMPLETE
PROSPECTIVE E5: PENDING / NOT_FROZEN
EXTERNAL VALIDATION: NOT ESTABLISHED
```

“Complete” refers only to the release-scoped engineering validation listed above. It does
not mean that financial conclusions are proven correct, calibrated, safe for production,
or suitable for regulatory use.
