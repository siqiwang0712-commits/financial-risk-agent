# v0.4.2 development experiments

Status: **RETROSPECTIVE_DEVELOPMENT / DESIGN_EXPOSED / POST_HOC_EXPLORATORY**.

This new derived directory does not replace any frozen E4, E4-S, E4-R or v0.4.1 result.
The selected StrongTabularReference-v1 OOF scores and verified historical labels describe
675 selected companies (235 events) from the previously analyzed development cohort.
Their source commit is pinned in `config.json`; this is the input snapshot identity,
not a claim that the new experiment runner existed in that historical commit. Runner
and current runtime identities are recorded separately by content hash. No retraining,
model reselection, calibration, external validation or prospective E5 execution occurs.

Run from the repository with its supported Python environment and research/test setup:

```bash
PYTHONPATH=backend python -m research.v042_experiments.run_diagnostics
PYTHONPATH=backend python -m research.v042_experiments.run_diagnostics --check
```

The first command writes only this new directory. The second independently recomputes
and compares results, manifest and summary. Historical input hashes are also bound to
Git source blobs. JSON input comparison normalizes CRLF to LF; separate original Git
blob hashes and repository attributes preserve historical source identities. No original
file is rewritten. New experiment files use LF for deterministic verification.

Artifacts: [configuration](config.json), [results](results.json), [manifest](manifest.json),
[human-readable summary](EXPERIMENT_SUMMARY.md).

The compute budget is five CPU minutes. The initial complete run took 0.64 seconds
and about 29 MiB maximum RSS; no network provider or model fitting is used. Configured
sizes are 675 OOF rows, five existing folds and six mock Agent runs. The fixed descriptive
thresholds and review budgets were chosen post-hoc for this analysis and never update
production policy. All metrics and denominators are defined in the configuration.

Completed: risk/coverage curves, analyst-budget event capture, and existing-fold error
variation. The mock repeatability harness verifies actual runtime certificates, but
is synthetic engineering evidence and cannot show reduced stochastic provider error.
Real-provider execution is **NOT_RUN_PROVIDER_UNAVAILABLE**. Historical full Assurance
ablations are **NOT_ESTIMABLE** without same-cohort Agent intermediate states. Additional
shift/subgroup/refitting work is **DEFERRED_NON_BLOCKING**. No missing intermediate
states, annotations, future cohorts, outcomes or E5 exclusion identities are invented.

An empty issued set has **NOT_ESTIMABLE** selective error. Empty evidence unions also
have **NOT_ESTIMABLE** Jaccard. Abstention is never counted as a correct prediction.
Diagnostic PASS/FLAG coverage is not an authorized decision rate. Scores remain
**UNCALIBRATED**, and provenance verification does not establish semantic truth.
E5 remains **BLOCKED / DRAFT_NOT_FROZEN**.
