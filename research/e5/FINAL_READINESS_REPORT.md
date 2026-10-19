# Structured E5 final readiness report — 2026-10-19

## Overall status

**BLOCKED**

This is a freeze-readiness audit, not a protocol freeze or E5 empirical result.
Autopilot != ScientificAuthority. No favorable result is assumed or required.
The [machine report](final_readiness.json) contains exact identities, unresolved
fields, arm metadata and commands. The [typed blocker register](autonomy/blockers.json)
contains each decision, insufficient evidence, missing information, confirmatory
risk, allowed next steps and prohibited shortcuts.

## Starting repository state and commit identity

- Branch: `E5-experiment`; clean at `6a6f2053dd168d74aa97533ad901af47a7a5023a`, identical to main then.
- Python: 3.12.14; requirements lock SHA-256 `a73ed331f9bb9c4c469f3bd7ae12cff80185315fc0e717c8bbca8817c7b22046`.
- Initial protocol/config/harness hashes are retained in `final_readiness.json`.
- Pre-audit implementation SHA: `6d47f31d8245cdd2e65f5efec5e83232d567b299`.
- The machine report separately records the exact tested audit/governance code hashes.
- Final SHA: resolve the commit containing this report with
  `git log -1 --format=%H -- research/e5/FINAL_READINESS_REPORT.md` and compare it
  with remote `E5-experiment`. Embedding this file's own containing SHA would
  change that SHA; the completion message reports the actual pushed final SHA.
- Current protocol SHA-256: `d7bb91b52ad138f637346938345ca83e85f22b70b3fc74ff25c1fac865f9eec1`.
- Current config SHA-256: `62a28c3e074da5cb75ca7b5b62655e9cca9d9b9f138f6188ae660858cd666ce0`.

## Authority and resolved design fields

Authority is `STUDY_PROTOCOL_DRAFT.md`, `experiment_config.json` and the active
`harness/e5_harness.py`. The Constitution constrains all of them. Legacy B6/A2/
Hybrid material cannot control a freeze; no legacy hypotheses were restored.
E5-Narrative remains separately blinded, annotated and evaluated, not executed.

| Previously open field | Outcome-blind resolution |
|---|---|
| Calibration | Explicit E5 UNCALIBRATED; no probability interpretation or weak calibration split |
| S0 design/fitted identity | Adopt exact existing historical fitted artifact, schema, preprocessing, hyperparameters, source and generation-environment hashes; no refitting |
| S1 selective rule | Retain predeclared historical `s1-fixed-review-band-v1`: FLAG >=.65, PASS <.35, otherwise REVIEW; no threshold search |
| Assurance/certificate nomination | Bind actual released v0.4.2 source, policy version/hash, certificate schema and replay/migration rule |
| P1/P2 and denominator | Comparator-minus-S4 erroneous automated incidence on common VERIFIED cases; coverage separately uses all eligible paired packets |
| Alpha/multiplicity | FWER .05, two-primary Holm step-down; secondary/post-hoc cannot rescue a failed primary |
| Inference blueprint | Paired company means, 20,000 paired bootstrap draws, seed 20261019, BCa intervals, null-centered plus-one p-values, intersection-union safety/coverage tests |
| Endpoint | Nominate forward deterioration v1 implementation and calendar-12-month anchor; explicit review/missing mapping, no negative imputation |
| Exclusion architecture | Versioned historical source registry and mandatory 2,000 development exclusions; unknown prior identities remain blockers |
| Governance | Constitution, strict state/identity guards, task ceiling, immutable writes, explicit amendments, dedicated CI |
| Qualification/TEVV | Future non-E5 qualification rule and separately identified robustness contract; no candidate study or reviewer fabricated |

**11 freeze-critical config paths remain unresolved**, listed exactly in the machine
report. They were not filled with arbitrary constants merely to claim readiness.

## Remaining blockers

| Scope | ID | Exact obstacle and allowed path |
|---|---|---|
| Protocol | E5-P01 | Released HEURISTIC_POLICY / UNCALIBRATED S4 never allows automation. Useful automated coverage needs a scientifically justified, independently approved design decision; do not weaken policy or relabel RESTRICTED outputs. |
| Protocol | E5-P02 | Released Agent verifies before proposal. Qualify a shared evidence-independent proposal producer and evidence-only intervention before claiming component attribution. |
| Protocol | E5-P03 | Meaningful error benefit, coverage NI margin and useful coverage floor lack independent loss/review-capacity evidence. Joint inference/power qualification cannot substitute an arbitrary favorable effect or N. |
| Protocol | E5-P04 | Historical empirical profile needs a qualified runtime adapter/scope, structured extraction and prospective prediction timing. A 12-month collection window is only a candidate until per-company/global freeze ordering prevents early outcome exposure. |
| Cohort | E5-C01 | Exact previous_270 is absent; no proved containing superset. Original E4/qualification/prior-validation company sets also need complete source-bound identities. This is not, by itself, a protocol-readiness blocker. |
| Future data | E5-F01 | Later authorized stages and independently controlled future outcomes are intentionally absent. |

## S0–S4 identity and proposal ablation

The candidate binding file contains exact hashes of adopted released runtime and
historical model components; it is **not** an executed protocol-freeze manifest.

- **S0:** VO histogram-gradient-boosting reference; fitted artifact
  `3e1ebd825f1699bcc88e52a531bf9199aad3e93a671cfe28640f15dd33759a26`. Output [0,1] uncalibrated ranking
  score; no final authority. Historical Python 3.12.14 / NumPy 2.5.3 / sklearn 1.9.1
  generation environment is retained separately from the v0.4.2 lock. E5 replay
  qualification is still required; historical development is not prospective proof.
- **S1:** exact S0 score plus the existing fixed .35/.65 band; no Agent/Full
  Assurance. Historical issuance 562/675 is recorded development evidence only.
- **S2:** full intended proposal producer remains unqualified; no model/prompt is
  invented or chosen by future outcomes. No product final authority.
- **S3:** candidate adapter consumes the identical proposal and checks material
  evidence only; no fragility/reference/full-policy/certificate authorization.
- **S4:** candidate adapter uses actual default Assurance and verifies a Decision
  Certificate. Policy hash `c0ce6ed4752c53e67f3528de1013a4a6ff4d512b1790cde1c6628b354c8b9053`;
  schema `decision-certificate-v0.4`. Automation remains withheld.

`Proposal_S2 == Proposal_S3 == Proposal_S4` is mechanically proven **for the
candidate shared-packet adapters on synthetic engineering fixtures**. It is **not
established for a qualified actual producer**. This distinction prevents copying an
already-verified Agent output from masquerading as scientific ablation isolation.

## Primary and secondary inference

Primary error indicator is an incorrect automated PASS/FLAG. Withheld cases can
have zero issuance incidents but are never counted as correct predictions.
Primary error denominator is the common paired VERIFIED endpoint set; coverage
uses all eligible paired packets. Report attrition and full-population worst-case
incident bounds; missing labels are never non-events. Benefit is lower erroneous
incidence with useful coverage, not a high AUROC or all-abstain accuracy.

P1=S4 vs S1; P2=S4 vs S3. Planned paired means/BCa inference and Holm are specified
in [INFERENCE_DESIGN.md](autonomy/INFERENCE_DESIGN.md). Each primary needs safety,
coverage noninferiority AND absolute useful coverage; use the maximum component
p-value before Holm. Exact null boundaries, qualification and joint power remain
blocked by missing utility constraints. Degenerate inference means NOT_ESTIMABLE.

AUROC, PR-AUC/prevalence and paired DeLong remain secondary on appropriate common
cases. Also report selective error, risk/error–coverage, fixed-review-budget event
capture, REVIEW/ABSTAIN, source support and out-of-reference issuance. No post-hoc
analysis upgrades failed primary evidence.

## Power and sample size

`autonomy/power_design.py` generated 144 analytic planning sensitivities covering
prevalence, evaluable fraction, paired schema success, error discordance, effect and
attrition. The previous 1200–1500 intention and roughly 100 paired positive-event
goal are evaluated as planning constraints, not blindly retained. Many sensitivity
rows require far more than 1500 cases even for safety alone. These are normal-
approximation paired-error bounds, **not joint IUT power**, a selected meaningful
effect or a final N. No E5 cohort or outcome simulation was generated. Zero current
S4 automation cannot be repaired by increasing N.

## Endpoint, calibration and prospective isolation

Adopt `sec_bulk.build_deterioration_labels`, forward deterioration v1 and
`add_twelve_months`, not the historical fixed-date E4 archive wrapper. Later raw
REQUIRES_HUMAN_REVIEW maps to REQUIRES_REVIEW; missing/insufficient stays unknown.
Two blinded reviewers and a third adjudicator are a future interface only.
Calibration stays UNCALIBRATED; external validation is NOT_ESTABLISHED.

Future packet guards bind CIK/accession, cutoff, source/period/unit/hash and source
availability <= cutoff; unknown fields and future timestamps fail closed. No
current/latest backfill is allowed. Prediction/outcome mounts need independent
operational review; path absence is not proof of OS isolation or reviewer blinding.
No actual outcome path was mounted/read in this work.

## Governance, amendments and repaired verification defects

The existing nine stage sequence numbers remain intact. The autonomy lifecycle
specifies future WAITING_FOR_OUTCOMES and independent audit gates without faking
those stages. This task's ceiling blocks actual protocol writes and all later
transitions. Post-prediction scientific amendments invalidate the affected identity;
exposure declarations cannot conceal already-frozen stages. Negative results cannot
license threshold changes or promotion of secondary evidence.

Five negatives failed before the harness fix: corrupt JSON ignored, unknown stage
ignored, duplicate stage overwritten, omitted protocol hash accepted, and omitted
cohort disjointness assertion unguarded. An additional reproduced validator defect
accepted an empty config by silently substituting the real config. All are now
rejected. Additional regressions cover UTC/sequence/root identities, exclusive
writes, path escape, missing model/analysis identity, future leakage, exact historical
exclusions, duplicate evidence, invalid scores, label coercion and amendment/claim
abuse. Existing positive fixtures now use an explicit synthetic qualified identity;
no failed assertion or security threshold was weakened.

## Test evidence and limitations

| Check actually executed | Result |
|---|---|
| Current contract validator | PASS, 60 checks |
| Existing freeze-chain verifier | PASS; every stage absent, NOT_FROZEN |
| New state/identity/autopilot checks | PASS for truthful BLOCKED, not readiness |
| `verify_state.py --require-ready` | Exit 2 as required; READY_TO_FREEZE rejected |
| Full relevant E5/Assurance/certificate/release-integrity pytest suites | **263 passed, zero skipped**, Python 3.12.14 |
| Ruff over backend/tests/scripts/research | PASS |
| v0.4.2 current/historical runtime identities and release metadata | PASS |
| Frozen E4 public verifier and historical preflight check | PASS; historical bytes/identities retained |
| `pip check`, Markdown links, `git diff --check` | PASS |
| New CI workflow YAML, matrix, read-only permissions and full SHA action pins | PASS static checks only |
| Local Python 3.11 | NOT RUN; no local interpreter available, dedicated remote matrix includes 3.11/3.12 |
| Full product/Docker/PostgreSQL/package release matrix | NOT RUN for this design change; unchanged existing CI/gates remain required |
| Aggregate v0.4.2 diagnostic runner | NOT RUN; avoid historical experiment recomputation, use immutable-byte checks instead |
| New-commit remote CI | Not pre-attested here; inspect exact final pushed commit |

One initial historical-source check exposed an LF working-tree checkout despite its
explicit CRLF Git attribute. Restoring Git-filtered checkout bytes matched the old
recorded SHA exactly, with no tracked diff or regenerated evidence. Early expected
negative-test logs and final engineering logs are retained under `/tmp/e5-*` in the
execution workspace; the commands and regression tests are the durable evidence.

## Critical final assertions

```text
COHORT = NOT_ENUMERATED
PREDICTIONS = NOT_GENERATED
OUTCOMES = NOT_ACCESSED
PROTOCOL FREEZE = NOT_EXECUTED
E5 VALIDATION = NOT_ESTABLISHED
CALIBRATION = UNCALIBRATED
```

Main, published history and frozen E1–E4/E4-S/E4-R/development artifacts were not
changed. No PR, tag, GitHub Release or prospective E5 execution was created.
The scientifically defensible result of this mandate is **BLOCKED**.
