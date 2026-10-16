# FinRisk v0.4.2 closeout audit

Audit date: 2026-10-15. Target: `origin/try-v0.4.2`, version **0.4.2**.
Starting commit: `7e9bd827a638c2aa992de9e193e39b82e451616c`.

Audited source commit: `e41638d8d02636127dc6f3fa6d4c2a72e07baca6`.
This dated engineering record is preserved across later documentation/presentation
commits; it does not attest new image bytes built from a later commit. Current
branch identity and new-commit CI must be checked separately. Status at closeout:
**READY FOR v0.4.2 RELEASE / PROMOTION**, not formally published.

Remote results rechecked during the narrative pass:

- [Ordinary CI 38769888323](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/38769888323): SUCCESS on the audited source.
- [Container dry-run 38769950209](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/38769950209): SUCCESS on the same source; prepare, both builds, scans, both runtime verifications and dry-run succeeded; publish SKIPPED.
- Neither result establishes tag creation, GitHub Release creation or production image publication. No research experiment was rerun for the narrative pass.

## Release-critical review and fixes

| ID | Class / severity | Root cause and failure | Fix / regression |
|---|---|---|---|
| EV-01 | Confirmed integrity defect / Medium | Non-narrative Assurance paths trusted VERIFIED without requiring nonempty source evidence; empty paths could contribute verified coverage. | Reuse the material-path check for every path and reject empty source records. Missing evidence yields ABSTAIN even if unknown fragility is permitted. Three negative cases failed before the fix. |
| EV-03 | Confirmed semantic integrity defect / Medium | A rehashed payload could claim verified paths but zero source IDs when the trusted policy permits unknown fragility. Certificate path rebinding already rejected it; the independent Assurance verifier did not. | Require source IDs whenever verified_path_count is nonzero. The self-consistent rehashed automated FLAG negative failed before the fix and is now rejected. |
| EV-02 | Confirmed integrity defect / Medium | Exact repeated paths counted repeatedly, inflating coverage and dependency multiplicity. | Canonical material-path deduplication in both evidence assessment and fragility dependencies. Ignore operational telemetry only; distinct claims/rules sharing a source remain separate. Duplicate-count negative failed before fix; transition and telemetry regressions pass. |

Reviewed dependency map: model/rules/Agent -> proposal -> AssuranceEngine ->
authorized final -> certificate -> tenant-scoped repository -> API -> guarded UI.
No valid Assurance result means no authorized final. Agent failure records withhold
positive decisions. Model/provider outputs do not acquire authorization authority.

The review covered provider redirect rejection (301/302/303/307/308), untrusted
metadata roles, bounded provider reads and input schemas; JSON/multipart admission,
PDF parsing isolation, worker cancellation and pre-write result quotas; policy,
calibration, blockers, reasons, evidence/fragility/distribution transitions; certificate
schema/content/path/policy binding and replay; tenancy/roles/credentials, PostgreSQL
migration/persistence/corruption rejection; frontend final/proposal guards and React
text rendering; wheel resources and runtime versions; CI prerequisites, source
identity, candidate digests, migration-image reuse and exact-digest scan/promotion.
Already-correct boundaries were retained rather than redesigned.

Provenance verification is not semantic truth. Exact duplicate dependencies do not
increase proof; distinct rules using the same evidence are not independent sources.
Default Assurance remains **HEURISTIC_POLICY / UNCALIBRATED**. Missingness remains
separate from financial values. Reference checks are deterministic applicability
constraints, not validated statistical OOD detection. Hashes provide integrity, not
issuer authentication; prompt injection remains residual and workers are not a
native-code security sandbox. Authentication and trusted storage remain required.

## Validation and evidence

Current-run commands/results are recorded below. A preliminary full run exercised 947 tests per interpreter before EV-03 was found; it is not final-source proof. The complete gate is rerun after that fix. Previous green
runs and the [historical security report](SECURITY_HARDENING_v0.4.2.md) do not prove
this new commit. No unexecuted gate is treated as passing.

| Local gate | Final result | Executed evidence |
|---|---|---|
| Focused Assurance/experiment tests | PASS | 87 focused cases (including real PostgreSQL); original missing-source/duplicate negatives failed before fixes |
| Python dependency audit | PASS | `pip-audit --strict --no-deps -r requirements.lock`; writable cache retry after setup error |
| Frontend complete inventory | FAIL / residual | Full `npm audit --json`: five HIGH entries for one unfixed dev-only braces advisory; no forced incompatible downgrade |
| Backend 3.11/3.12 + coverage | PASS | 948 tests per interpreter, zero failures/errors/skips; 92.20% coverage each, 90% threshold retained |
| Frontend build/tests/types/lint/production audit | PASS | Locked install; 36 tests; lint/types/build; production npm audit zero |
| Packaging and outside-checkout installs | PASS | Wheel and sdist; clean Python 3.11/3.12 installs; pip check; outside-checkout API/Assurance/certificate verification with package/API version 0.4.2 |
| PostgreSQL/container/both Compose/runtime | PASS | API/web builds; identity/privilege checks; exact-image API/web/migrate; both Compose stacks; 16 PostgreSQL tests, idempotent migration, restart persistence/certificate/replay; HTTP 401/413/415/422/429 and 504 twice |
| Fresh source/image policy scans | PASS | Trivy 0.68.2, official DB updated 2026-10-15T13:13:18Z; source and exact final API/web images: zero fixable MEDIUM/HIGH/CRITICAL vulnerabilities and zero secrets |
| Unfiltered image inventory | FAIL / residual API | Fresh unfiltered HIGH/CRITICAL scans: API 40 HIGH findings across eight CVEs with no FixedVersion, zero CRITICAL; web zero HIGH/CRITICAL. Scanner execution/schema/image binding passed |
| Research/provenance/E5 | PASS | verify_v042 --ci; frozen E4; E4-S 44/44; E4-R 136/136; StrongTabularReference 27110 checks and 10-row replay; E5 remains BLOCKED / DRAFT_NOT_FROZEN; new derived results reproduce |
| Static/version/documentation | PASS | Ruff; git diff --check; current 0.4.2 metadata; 73-document link check; source snapshot retained through final full gate |

## NON-BLOCKING EXPERIMENTAL PROGRESS

New derived artifacts live only in [v0.4.2 experiments](../research/v042_experiments/README.md).
[Summary tables](../research/v042_experiments/EXPERIMENT_SUMMARY.md),
[configuration](../research/v042_experiments/config.json),
[results](../research/v042_experiments/results.json) and
[verification manifest](../research/v042_experiments/manifest.json) record inputs,
source commit, code/current-runtime identities, timestamp, no-sampling seed status,
metric definitions and result/evidence classes. Historical source bytes are preserved.

| Experiment | Status | Dataset / artifact | Compute | Evidence class / key finding | Production effect |
|---|---|---|---|---|---|
| V042-RC-01 risk/coverage | COMPLETE | Frozen selected VO OOF; results.json | 675 rows, six thresholds | RETROSPECTIVE_DEVELOPMENT / DESIGN_EXPOSED / POST_HOC_EXPLORATORY; 100% diagnostic coverage has 18.96% error; distance 0.4 has 45.19% coverage and 5.57% selective error | None; no authorization/policy update |
| V042-BUDGET-01 review budget | COMPLETE | Same OOF cohort | Three budgets | Same exploratory class; 135/675 reviews capture 120/235 historical events (51.06%) | None; no realized-profit claim |
| V042-FOLD-01 existing-fold errors | COMPLETE | Same OOF and original five folds | No refitting | Same exploratory class; fixed-threshold errors range 16.30%-22.22%, N=135 per fold | None; no seed/generalization guarantee |
| V042-AGENT-01 repeated runs | MOCK_HARNESS_ONLY | Existing synthetic fixture, with/without pages | Two scenarios x three runs; full initial batch <1 second, about 29 MiB RSS | SYNTHETIC_ENGINEERING_ONLY; identical proposal/final values, verified certificates, automation false; empty evidence Jaccard NOT_ESTIMABLE | None; cannot estimate real-provider instability reduction |
| Real-provider repetition | NOT_RUN_PROVIDER_UNAVAILABLE | No configured API-key or mounted-key binding | No paid/external calls | NOT_RUN | None; non-blocking |
| Historical Assurance ablation | NOT_ESTIMABLE | OOF has no same-cohort Agent evidence/fragility/Assurance intermediates | Admission inspected; no invented arms | NOT_ESTIMABLE | None; non-blocking |
| Additional shift/subgroup/refit trials | DEFERRED_NON_BLOCKING | Existing historical diagnostics retained | Avoid feature reconstruction and extra model fitting | NOT_RUN | None |

The development set was selected for verified labels and repeatedly analyzed. These
are descriptive development results, not population/external/prospective validation.
Score distance is not a calibrated probability. Zero issued decisions means
NOT_ESTIMABLE selective error; abstention is never counted as correct prediction.
StrongTabularReference-v1's winner, fitted files, selection record, historical metrics
and hashes remain unchanged and honestly labeled. E5 remains **BLOCKED /
DRAFT_NOT_FROZEN**; no future cohort/outcome or unavailable 270-company exclusions
were invented. Software readiness and experimental evidence are separate.

## Residual risks and publication boundary

Known dev-only advisory GHSA-vfj7-8cjw-p6xm remains a failing supplemental full npm
inventory until a compatible fix exists. The production dependency audit remains
mandatory. Fresh unfiltered base-image findings are recorded with final validation;
no scanner suppression or threshold reduction is permitted. Real provider behavior
cannot be claimed from mock execution. This audit is not external certification.
No Git tag, GitHub Release, production image publication, main modification, merge,
E5 execution/freeze or historical artifact regeneration is part of this closeout.

## Final local evidence identities and remote completion

Final aggregate: `python -m scripts.verify_v042_release --python311 <3.11>
--python312 <3.12> --prune-build-cache`. Cloud-specific build options supplied the
existing host proxy and CA bundle without disabling TLS/signature checks. Numeric
libraries used one thread each to avoid CPU oversubscription; both complete suites
still ran in parallel. No test or audit threshold changed.

Log: `/tmp/finrisk-closeout-release-gate-final.log`. The earlier 947-test run,
previous 2026-10-09 gate directory, initial failing regression logs and old local
images were preserved separately; none is substituted for this final-source run.
Transient execution-connection interruptions recovered without losing the tests.

Local candidate image IDs below identify configuration objects, not registry digests.
Remote exact-commit CI and `version=v0.4.2, publish=false` were separate checks after
the audited source push; verified run links are at the top of this report. These
results attest that source only; this file does not pre-attest later commits. Verify `gh run list --workflow ci.yml --commit "$(git rev-parse HEAD)"`
and the container workflow's actual job inventory before PR. Publishing must be skipped.

- api: `sha256:3b7f90e1598c38a1c6475b4eeb179a12d75f17f50977f7a084f4483d6ee8b00e`
- web: `sha256:e8c3487abb4b253954f018a26c0fb826bc07c8d31d5792cece3996486ba72c3b`

Current evidence SHA-256 records:

- final-source-snapshot: `d0f6bcd99e63e3d22254864b49ded9514f5d2d29fb7b910520043feb87d7b70c`
- aggregate-log: `f31357590c7e456a45f9fecefb450403f5623e7dcd69a23b44149d77e4258df1`
- source-scan: `89562230378825e99e33536b4d3111d7dac067ce99ddcc09bbfe1853f118d566`
- API-policy-scan: `a56eb5f3a4934f4347d15a67da8e93c83d41eb62ca7d88015a297697a2e7c856`
- web-policy-scan: `3884f5c6394b154aaeef8dbbd75669e97b8e15c79bee35a5ae11e3e2c73f601d`
- API-unfiltered-scan: `6d6369e1871e2066b262669c5758a8f73b0afb1221290dcb34c72839d643b21c`
- web-unfiltered-scan: `deeed7a0ee0de9ed123597fd45de34e3775ef39b803ea0fc7505bde9d2d3e394`

The final API CVEs remain CVE-2025-69720, CVE-2026-16742, CVE-2026-54369,
CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 and CVE-2026-9538.
No application request exploit was established; this is not proof of unreachability
or a clean base-image claim. The dev-only braces registry latest remains 3.0.3;
the suggested forced Next/ESLint 14 downgrade is not a compatible security fix.
Retain both residual inventories and rescan before production promotion.
