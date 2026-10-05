# E5 — Prospective Validation of Assured Selective Financial Decisions

Status: **BLOCKED / DRAFT_NOT_FROZEN**

No E5 cohort, prediction, label, result, preregistration hash or freeze manifest exists.
The authoritative human draft is [`STUDY_PROTOCOL_DRAFT.md`](STUDY_PROTOCOL_DRAFT.md);
its machine-readable companion is [`experiment_config.json`](experiment_config.json).
Those are the only current structured-E5 study-contract files eligible for a future
protocol freeze after their explicit blockers are resolved.

E5 asks whether Assurance improves selective authorization quality and utility on a
future, company-disjoint cohort while retaining a competitive predictive reference. It
does not reduce Assurance to AUROC and does not assume that withholding decisions improves
prediction.

## Current five-arm design

| Arm | Conceptual role |
|---|---|
| `S0` | Strong Tabular Predictor selected prospectively under `StrongTabularReference-v1` |
| `S1` | S0 plus a prospectively frozen simple selective policy |
| `S2` | Raw Agent proposal with no final-decision authority |
| `S3` | S2 plus evidence verification, excluding the remaining Full Assurance controls |
| `S4` | Full FinRisk Assurance: evidence, fragility, distribution validity, admission policy and certificate-bound authorization |

B0 and B6 remain historical reference and interpretability anchors. They may be reported
for E4 continuity, but neither is S0 or the strongest competitive reference.

[`StrongTabularReference-v1`](../strong_tabular_reference/README.md) now has a fitted,
replayable `DESIGN_EXPOSED` historical-development artifact. It remains
`DRAFT_NOT_FROZEN` for E5: its E5 identity is not frozen and its development metrics are
not prospective evidence. E4-R informed the candidate design but cannot validate E5.

## Structured and narrative studies

Structured E5 asks when a financial-risk decision should be authorized, reviewed or
withheld. [`E5-Narrative`](narrative/NARRATIVE_PROTOCOL.md) separately asks whether an Agent
can extract, ground, cite and verify claims in filing text. The studies retain separate
protocols, configs, datasets, freeze identities, metrics, claims and future results.

## Legacy protocol package

The materials under [`protocol/`](protocol/) are preserved rather than rewritten as
history. They cannot control a future structured-E5 freeze.

| Legacy material | Current role |
|---|---|
| `protocol/STUDY_PROTOCOL.md` and `protocol/experiment_config.json` | superseded B6/A2/Hybrid scientific design; not freeze candidates |
| `protocol/INFERENCE_POLICY.md` | reusable paired-inference, resampling and multiplicity guidance; old hypotheses superseded |
| `protocol/AGENT_REPRESENTATIONS.md` / `representations.json` | reusable A0–A3 confound evidence; do not select S2/S3 |
| `protocol/AGENT_QUALIFICATION_PROTOCOL.md` | reusable outcome-blind qualification gates; exact S2 identity remains open |
| `protocol/OUTCOME_ADJUDICATION_PROTOCOL.md` | reusable blinding and non-coercion mechanics; exact version remains open |
| `protocol/GOVERNANCE_WORKFLOW.md` / `verify_freeze_chain.py` | legacy governance design; the active registry is `harness/e5_harness.py` |
| `protocol/power_analysis.py` / `power_analysis.json` | legacy AUROC planning infrastructure; not the power basis for the new authorization primary family |

The active harness now hashes the top-level authoritative draft and config. It reports
`NOT_FROZEN` until a later, explicitly authorized protocol-freeze operation occurs.

## Current blockers

Before protocol freeze, the project must still bind the historical reference into the E5
identity and finalize the calibration disposition, E5 reference-distribution design, Assurance policy and
certificate versions, primary authorization estimand, multiplicity alpha, meaningful
effects/thresholds, eligibility/timing logic and S2/S3 identity.

The missing prior 270-company list remains a later cohort-freeze blocker. No list is
invented here.

See the [readiness audit](../e5_readiness/READINESS_AUDIT.md) and
[phase-specific blocker list](../e5_readiness/BLOCKERS.md).

Validate current contract consistency without freezing anything:

```bash
python research/e5/validate_study_contract.py
python research/e5/harness/verify_e5.py
```
