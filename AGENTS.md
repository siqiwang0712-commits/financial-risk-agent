# Repository scientific-integrity rules

For Structured E5 use `research/e5/STUDY_PROTOCOL_DRAFT.md`, its
`experiment_config.json`, and the active `harness/e5_harness.py`. Read
`research/e5/autonomy/E5_CONSTITUTION.md` before changing E5. Legacy `protocol/`
is design history, never freeze authority. E5-Narrative is a separate study.

- Work for this mandate only on the existing `E5-experiment` branch. Never modify
  main, create a replacement branch, merge or open a PR.
- Stop at READY_TO_FREEZE, or report BLOCKED with machine-readable reasons. Do not
  freeze the protocol, enumerate prospective companies, generate E5 predictions,
  mount/read future outcomes or execute prospective E5.
- Historical E1–E4/E4-S/E4-R, fitted references and frozen hashes are immutable.
  Do not refit models or regenerate historical outputs to satisfy a check.
- Outcome-blind analytic **planning** and temporary synthetic engineering tests
  are permitted; neither is E5 evidence. Never fabricate reviewers or exclusions.
- Null/negative results are legitimate. Never weaken gates, change scientific
  choices after evidence exposure, or tune a study to make FinRisk win.
- Use `python research/e5/autonomy/e5_autopilot.py --check` for design-integrity
  checks. Exit 0 means the declared BLOCKED/READY state is truthful, not that E5
  is ready. `verify_state.py --require-ready` must fail for BLOCKED.
- Do not run the aggregate v0.4.2 research verifier blindly: it recomputes old
  diagnostics. Prefer hash-only preservation checks and engineering tests here.
