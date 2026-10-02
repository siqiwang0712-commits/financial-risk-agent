# v0.4 Development Validation

Status: **RETROSPECTIVE DEVELOPMENT ONLY — NOT CONFIRMATORY**

This area records engineering-validation plans for the v0.4 Assurance Runtime. It must not
contain prospective E5 outcomes or be cited as a confirmatory experiment.

Current validation is limited to:

- synthetic, deterministic Assurance fixtures;
- authorization-bypass and fail-closed tests;
- evidence monotonicity and leave-one-evidence-out determinism;
- exact/approximate sufficient-evidence contracts;
- distribution-validity monotonicity;
- financial/reporting feature separation;
- certificate mutation and replay checks;
- historical artifact-integrity verification.

The release-scoped result and exact maturity boundary are recorded in
[VALIDATION_REPORT.md](VALIDATION_REPORT.md). The synthetic
[`development_reference.json`](development_reference.json) is
`DEVELOPMENT_REFERENCE_ONLY`; it is not a population reference or external validation.

No large cohort, new dataset, LLM sweep, hyperparameter search or model leaderboard was
run for v0.4. Any later retrospective artifact added here must carry all four labels:
`RETROSPECTIVE`, `POST_HOC`, `DEVELOPMENT`, `NOT_CONFIRMATORY`.
