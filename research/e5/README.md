# E5 — Confirmatory Study Preparation

E5 is protocol-only. No cohort, prediction, label, result, or research claim
exists yet. E4 outcomes are already known, so neither unused E4 companies nor
post-hoc E4 model/prompt/fusion choices may receive confirmatory status.

E5 must use a newly available future period, freeze all decisions before
outcome access, and remain company-disjoint from E1–E4 and prior validation
cohorts.

## Protocol package

`STUDY_PROTOCOL_DRAFT.md` is the original E4-era draft, retained as history.
The freeze candidate lives in `protocol/`:

| File | Purpose |
|---|---|
| `protocol/STUDY_PROTOCOL.md` | the protocol itself: isolation, estimand, systems, hypothesis hierarchy, power, adjudication, governance |
| `protocol/INFERENCE_POLICY.md` | prespecified primary inference, permitted secondary procedures, forbidden procedures |
| `protocol/AGENT_QUALIFICATION_PROTOCOL.md` | outcome-blind model selection and its hard gates |
| `protocol/OUTCOME_ADJUDICATION_PROTOCOL.md` | blinded two-tier adjudication and its reporting requirements |
| `protocol/GOVERNANCE_WORKFLOW.md` | the nine stage commits and the freeze-manifest schema |
| `protocol/experiment_config.json` | the machine-readable freeze payload |
| `protocol/power_analysis.py` | simulation-based prospective power analysis |
| `protocol/power_analysis.json` | its output: power curves, recommended cohort, attrition sensitivity |
| `protocol/verify_freeze_chain.py` | mechanical verifier for the staged freeze chain |

`protocol/` is written but **not frozen**. Nothing here has a cohort, a
prediction, a label or a result.

## Status of the freeze prerequisites

Ready:

- hypothesis hierarchy H1/H2/H3 with Holm multiplicity over a three-test primary family;
- primary test fixed to paired DeLong, with the label-permutation design explicitly
  excluded as a test of AUROC equality (see `research/e4_statistical_audit/`);
- one-company-per-semantic-request inference policy;
- Agent qualification gates and lexicographic selection rule;
- blinded adjudication protocol with a disagreement rule;
- staged, hash-chained governance workflow with a verifier.

Blocking:

- **`research/e4/_cache/previous_270.json` is unpublished** (only its SHA-256 is pinned),
  so company-disjointness against the prior 270-CIK cohort cannot be proven. This must be
  published before the cohort freeze.
- The minimum meaningful ΔAUROC is a design choice that must be declared in the freeze
  commit; the power analysis reports a curve so the choice can be defended.
- The E5 feature and outcome periods must actually become available before the cohort can
  be enumerated.
