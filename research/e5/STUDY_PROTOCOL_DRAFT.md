# E5 — Prospective Validation of Assured Selective Financial Decisions

Status: **DRAFT_NOT_FROZEN — AUTHORITATIVE E5 STUDY CONTRACT**

`E5_PROTOCOL_FREEZE_ALLOWED = false`

This file is the single human-readable authority for a future structured E5 freeze. Its
machine-readable companion is [`experiment_config.json`](experiment_config.json). Neither
file is a preregistration or frozen protocol: no cohort has been enumerated, no prediction
has been generated, no future outcome has been accessed, and no final hash exists.

The older documents under [`protocol/`](protocol/) are preserved as legacy design material.
Their statistical, adjudication, isolation and hash-chain mechanisms may be reused only
where this contract or a future approved amendment explicitly adopts them. Their former
B6/A2/Hybrid hypotheses and fixed-Hybrid design are superseded and cannot control a future
freeze.

## 1. Purpose and evidence boundary

E5 is intended to prospectively evaluate whether Assurance improves the safety and utility
of selective financial decisions on a future, company-disjoint cohort while retaining a
competitive predictive reference.

“Safety” is not assumed or universally established. Where this draft uses authorization-
quality or unsafe-authorization language, it refers only to operational metrics defined in
this protocol and later frozen for this experiment. It does not imply regulatory safety,
production fitness or external validation.

E5 separates five questions that must not be collapsed:

1. **Predictive discrimination:** how well a score ranks a prespecified future endpoint.
2. **Calibration:** whether a score has an empirically supported probabilistic meaning.
3. **Selective behavior:** which cases are issued, reviewed or withheld at what error and
   coverage.
4. **Evidence support:** whether material claims and decisions have verified evidence paths.
5. **Authorization:** whether a proposal is permitted to become a final decision.

A higher AUROC does not validate evidence support, admission policy or Assurance. Assurance
does not improve prediction merely because it withholds decisions; any predictive change
must be measured separately on an appropriate common evaluable cohort.

The endpoint remains a versioned forward financial-deterioration endpoint. It is not a
bankruptcy, default, credit-loss or insolvency probability, credit rating, fraud finding or
investment recommendation.

## 2. Prospective isolation

- Feature and outcome periods must be later than E4 and unavailable when their respective
  freeze stages occur.
- Companies must be disjoint from E1–E4, public-pilot, historical-development and prior
  validation cohorts. An unused E4 company is not prospective.
- Prediction processes receive only prediction-time inputs. Outcome storage remains
  inaccessible until the content-addressed prediction/certificate freeze verifies.
- The unpublished `research/e4/_cache/previous_270.json` is a cohort-freeze blocker, not a
  reason to invent an exclusion set and not, by itself, a protocol-design blocker.
- Eligibility windows, sampling logic, salt and point-in-time rules remain `TO_BE_FROZEN`.
  No candidate enumeration is permitted while they remain open.

## 3. Required comparison arms

Exactly these five conceptual arms must be represented. Exact implementations are future
freeze items and may not be selected using E5 outcomes.

### S0 — Strong Tabular Predictor

The competitive predictive reference selected prospectively under
[`StrongTabularReference-v1`](../strong_tabular_reference/README.md). S0 produces a risk
score/proposal but has no Assurance authorization layer.

The reference contract remains `DRAFT_NOT_FROZEN` for E5, while v0.4.1 now provides a
mechanically selected, fitted **historical development** artifact. That artifact is
`DESIGN_EXPOSED` and does not itself freeze S0 for E5. E4-R motivated the candidate design;
historical AUROC may not be used for unrestricted winner shopping. Before E5 predictions,
the selected schema, preprocessing, model/config, software environment and artifact hashes
must become part of E5's frozen identity.

The outcome-blind artifact design is specified by
[`strong_tabular_reference/artifact_manifest.template.json`](../strong_tabular_reference/artifact_manifest.template.json)
and its draft [`contract_identity.json`](../strong_tabular_reference/contract_identity.json).
The contract hash identifies the design only. The historical fitted-artifact hash is bound
in `artifacts/artifact_manifest.json`, while the later E5 freeze identity remains
`TO_BE_FROZEN`; none is interchangeable with another.

Historical S0 fitting or selection required an
`APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT` manifest conforming to
[`development_data_manifest.template.json`](../strong_tabular_reference/development_data_manifest.template.json).
The approved manifest binds 675 labelled development companies and a conservative
2,000-company source-cohort exclusion. Every one of those 2,000 companies must become an
input exclusion for the future E5 cohort builder; E5 cohort enumeration must not begin by
consulting outcomes.

### S1 — Strong Tabular Predictor + Selective Policy

S1 applies a simple, prespecified selective-admission policy to S0. Its purpose is to
isolate the value of selective admission from Agent reasoning and Full Assurance. The
thresholds, review/abstain rules, calibration assumptions and policy identity are
`TO_BE_FROZEN`; this draft invents none of them.

S1 is deliberately stronger than an unconditional-prediction comparator but does not gain
Agent reasoning, claim verification, evidence fragility or the complete Assurance Runtime.

### S2 — Raw Agent Proposal

S2 is the outcome-blindly selected Agent configuration operating on a frozen representation
and prompt. It may emit a score and `proposed_decision`; it never owns final authorization.
The exact model, representation, prompt, runtime and retry policy remain `TO_BE_FROZEN`.
Legacy A0–A3 work may inform this choice but does not choose it here.

### S3 — Agent + Evidence Verification

S3 adds claim/evidence admission to the same frozen S2 proposal path. It may verify source
identity, citation/path existence and material-claim support, then withhold or route an
unsupported proposal according to a frozen evidence-only policy.

S3 must not include deterministic evidence-ablation fragility, distribution/reference
validity, the complete admission policy or certificate-bound Full Assurance authorization.
Those controls belong to S4. This boundary isolates the incremental effect of evidence
verification rather than quietly reproducing Full Assurance.

### S4 — Full FinRisk Assurance

S4 is the complete v0.4 path: evidence assurance, deterministic fragility analysis,
distribution/reference validity, versioned admission policy and certificate-bound
authorization. Only S4 represents Full FinRisk Assurance. It may issue a final decision
only through a valid `AssuranceResult` and Decision Certificate.

S4 is implemented and internally engineering-validated. It is not prospectively or
externally validated, and this protocol does not presume that it will outperform another
arm.

## 4. Historical anchors

B0 and B6 are historical reference and interpretability anchors. They may be reported for
continuity with E4, but they are not the strongest current competitive reference, are not
S0, and do not enter the confirmatory primary family. Their historical results and caveats
remain unchanged.

The legacy fixed Hybrid and A2-versus-B6 questions are also excluded from the current
primary family. They may support secondary historical diagnostics only if prospectively
declared.

## 5. Comparison map

The design avoids an uncontrolled all-pairs comparison surface:

| Comparison | Question | Planned role |
|---|---|---|
| `S1 vs S0` | Does simple selective admission improve the error/coverage trade-off relative to unconditional S0? | key secondary |
| `S3 vs S2` | Does evidence verification reduce unsupported or erroneous issued decisions relative to the same raw Agent proposal path? | key secondary |
| `S4 vs S3` | What do fragility, distribution validity, full admission policy and certificate-bound authorization add beyond evidence verification? | confirmatory candidate `P2` |
| `S4 vs S1` | Does Full Assurance improve authorization quality beyond a strong predictor with a simpler selective policy? | confirmatory candidate `P1` |

Other pairwise comparisons are secondary, sensitivity-only or descriptive unless a future
protocol amendment justifies and freezes them before the cohort is enumerated.

## 6. Estimand families

### A. Predictive discrimination

- AUROC on a common evaluable cohort;
- PR-AUC with event prevalence reported;
- paired differences only when both arms define comparable scores on identical cases.

Paired DeLong and company-cluster bootstrap infrastructure from E4-S/E4-R may be reused
when its assumptions match the estimand. Discrimination is not the primary evidence for
Assurance authorization quality.

### B. Selective behavior

- decision coverage;
- selective error/risk at reported coverage;
- risk–coverage or error–coverage curves;
- REVIEW and ABSTAIN rates;
- coverage conditional on prespecified data-availability and subgroup strata.

The exact loss, coverage targets, thresholds and aggregation rule are `TO_BE_FROZEN`.
Withheld cases are not silently counted as correct predictions.

### C. Authorization quality

Candidate operational measures are:

- **unsupported authorized decision rate:** authorized decisions lacking the frozen minimum
  verified-evidence support, divided by authorized decisions with assessable support;
- **erroneous authorized decision rate:** authorized decisions inconsistent with the
  frozen endpoint/adjudicated outcome, divided by authorized decisions with evaluable
  outcomes;
- **out-of-reference authorization rate:** decisions authorized when the frozen reference-
  validity rule classifies the case outside its asserted scope.

The future protocol must nominate one primary authorization-quality estimand, its
denominator, missingness treatment and direction before freeze. No composite “safety
score,” minimum effect or decision threshold is chosen here.

### D. Evidence behavior

- verified evidence coverage for structured material paths;
- unsupported-claim admission within the structured decision packet;
- correctness of machine-checkable structured evidence paths;
- deterministic fragility state and decision-flip behavior.

These measures are limited to evidence represented in structured E5 packets and dependency
graphs. They do not establish that the Agent can read or cite full filing text; that is the
separate E5-Narrative study.

### E. Calibration

Calibration metrics are confirmatory only if a valid company- and time-disjoint
development/calibration/final-validation design is frozen before E5 evaluation. Otherwise
every score remains `UNCALIBRATED`, Brier/ECE/reliability displays are descriptive only,
and no probability interpretation is permitted. The calibration blocker is not solved by
this contract.

## 7. Hypothesis and multiplicity hierarchy

### Confirmatory primary family

The intended small family is:

- `P1`: `S4 vs S1` on the single frozen primary authorization-quality estimand.
- `P2`: `S4 vs S3` on that estimand, or a separately justified component-increment
  estimand if frozen before cohort construction.

Both hypotheses currently have status `TO_BE_FROZEN`. The exact nulls, estimators,
minimum meaningful effects, family-wise alpha and decision thresholds are unresolved.
Holm step-down is the nominated multiplicity method over `P1` and `P2`, but it becomes
binding only when the estimands and family-wise alpha freeze. Statistical tests must follow
the data/estimand; the old AUROC test is not reused merely because code exists.

### Key secondary family

- `S1 vs S0` selective error/coverage;
- `S3 vs S2` evidence and authorization behavior;
- AUROC and PR-AUC on common evaluable cohorts;
- evidence coverage/path behavior;
- REVIEW/ABSTAIN characteristics and prespecified component ablations.

Multiplicity handling for any promoted secondary family is `TO_BE_FROZEN`. Analyses not
promoted before freeze remain secondary and cannot support a primary claim.

### Sensitivity and descriptive analyses

Threshold sweeps, alternative missing-outcome treatments, subgroup views, historical
B0/B6 comparisons and reweighting are sensitivity or descriptive analyses. Reweighting
cannot replace missing outcomes. Post-hoc analyses must be labelled `POST_HOC` and cannot
upgrade a failed primary result.

## 8. Structured E5 and E5-Narrative

Structured E5 asks:

> When should a financial-risk decision be authorized, reviewed or withheld?

[`E5-Narrative`](narrative/NARRATIVE_PROTOCOL.md) asks:

> Can the Agent correctly extract, ground, cite and verify claims from financial-report
> text?

They keep separate protocols, configs, datasets, freeze identities, metrics, claims and
results. Structured evidence-path metrics do not substitute for claim-level narrative
grounding, and narrative accuracy does not validate structured authorization behavior.

## 9. Outcome and coverage

The endpoint implementation, timing, deterministic verification rules and blinded review
protocol must freeze before outcome access. REVIEW cases require blinded adjudication;
INSUFFICIENT cases are never coerced to binary labels. VERIFIED/REVIEW/INSUFFICIENT
coverage, attrition and prediction-time availability covariates must be reported.

Legacy [`OUTCOME_ADJUDICATION_PROTOCOL.md`](protocol/OUTCOME_ADJUDICATION_PROTOCOL.md)
contains reusable blinded-review mechanics, but its exact version and any required changes
remain `TO_BE_FROZEN` under this authority.

## 10. Governance and freeze chain

The active harness is [`harness/e5_harness.py`](harness/e5_harness.py). Its nine stages are:

1. protocol;
2. model qualification;
3. cohort freeze;
4. feature-packet freeze;
5. prediction freeze;
6. outcome unlock;
7. adjudication freeze;
8. statistical analysis;
9. final report.

Each stage is content-addressed and chained to the previous manifest. Outcome-bearing
artifacts are forbidden before outcome unlock. A protocol-stage manifest must hash this
file and `research/e5/experiment_config.json`, not the legacy B6/A2/Hybrid documents.

The legacy governance workflow and verifier under `protocol/` remain useful design
history, but the active harness defines current stage names and freeze behavior.

## 11. Protocol-freeze prerequisites

`E5_PROTOCOL_FREEZE_ALLOWED` may become `true` only after every item below is resolved in
both this document and the machine config:

- [x] one authoritative human protocol and one current machine config are reconciled;
- [ ] StrongTabularReference-v1 design, candidate grid, development-data identity,
  selection rule and artifact format finalized;
- [ ] calibration resolved as either a valid disjoint design or explicitly
  `UNCALIBRATED` for E5;
- [ ] empirical reference-distribution design and scope finalized;
- [ ] exact Assurance policy version and hash nominated;
- [ ] exact Decision Certificate schema/version and migration rule nominated;
- [ ] primary authorization estimand, nulls and denominators finalized;
- [ ] multiplicity family, method and family-wise alpha finalized;
- [ ] minimum meaningful effects and decision/selective thresholds finalized where needed;
- [ ] eligibility, timing and point-in-time logic sufficiently specified for later cohort
  construction;
- [ ] Agent model/representation/prompt qualification rules reconciled with S2/S3;
- [ ] no ambiguous `TO_BE_FROZEN` design field remains in a freeze-critical position.

The prior 270-company exclusion list is required before **cohort freeze**, not necessarily
before protocol freeze. It must remain fail-closed at the cohort stage.

## 12. Current status and permissible claims

Current machine state:

```text
STUDY CONTRACT: AUTHORITATIVE DRAFT
PROTOCOL FREEZE: BLOCKED / NOT_FROZEN
COHORT: NOT_ENUMERATED
PREDICTIONS: NOT_GENERATED
OUTCOMES: NOT_ACCESSED
STRONG REFERENCE: DRAFT_NOT_FROZEN / NO FITTED ARTIFACT
CALIBRATION: UNCALIBRATED / DESIGN UNRESOLVED
EXTERNAL VALIDATION: NOT_ESTABLISHED
```

Negative or mixed findings would be valid future outcomes. Even a correctly completed E5
cannot by itself establish universal, production, regulatory or safety validity.
