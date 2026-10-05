# v0.4.1 final release audit

Status: **RELEASE CANDIDATE — NOT RELEASED**. No tag, GitHub
Release or container release-tag publication has been performed. Engineering readiness
does not establish prospective, external, production, regulatory or calibrated validity.

## Evidence identity

The reviewed release fixes are in `85e0e5dac5015c41973acf42cd03aa110789f46a`,
`dd2f03aa885444b6b3f6fce7a953d8b04ea961c5` and
`b91462742b30e8271eff27f2bca5c1225588a3bd` on `try-v0.4.1`. Later audit-document
commits do not change the tested runtime. Final remote checks must still target their
exact HEAD, because OCI source identity changes even for documentation-only commits.

## Issues and disposition

| Area | Finding | Disposition |
|---|---|---|
| Upload admission | Multipart files were parsed/spooled before authentication and the file ceiling. | Authenticate before reading; measured aggregate ceiling plus 64 KiB framing; 30-second body budget; two requests per process; retain file/page/text/worker limits. |
| Numeric proof | A verified quotation could label a contradiction verified without numeric provenance. | Bind every adverse current/prior input; reject legacy quote-only paths in Assurance and case proof/evidence readers. |
| Assurance payload | A recomputed hash did not reject non-boolean automation or policy-blocked fragility states. | Structural and policy consistency checks now fail closed; hashes remain integrity checks, not issuer signatures. |
| Workbench | Matching null/undefined decision fields could escape the presentation helper. | Missing/invalid authorization stays `UNAUTHORIZED`; never fall back to the proposal. |
| Mounted LLM secret | `OPENAI_API_KEY_FILE` was documented but not read by the provider. | Use the existing file-secret helper; file precedence and unreadable-file failure are tested. |
| Secret wording | File precedence was incorrectly described as removing inline environment secrets. | Clarify that inline DSNs/secrets still appear in container inspection; operators must mount files and remove inline values. |
| Local release gate | Interpreter identities, dependency audits and outside-checkout wheel imports were not all enforced. | Verify interpreter versions, audit both stacks, assert installed resources, isolate Compose cleanup, retain the 90% threshold and all checks. |
| Metadata | Released v0.4.0 was still `Unreleased`; workflow examples used earlier release identifiers. | Record its actual 2026-10-02 release date; use generic workflow labels/current dry-run examples. v0.4.1 remains unreleased. |
| Verification prose | Old local test/coverage totals were duplicated. | Centralize the current evidence here; distinguish local, normal CI and digest-bound release checks. |

## Local verification, 2026-10-05

| Check | Actual result |
|---|---|
| Python 3.11.16 full pytest | 762 passed, 18 skipped, 84 warnings; 91.09% line coverage; 510.25 seconds |
| Python 3.12.14 full pytest | 762 passed, 18 skipped, 84 warnings; 91.09% line coverage; 382.22 seconds |
| Required coverage | Unchanged: at least 90% |
| Ruff | Pass: `backend tests scripts research` |
| Dependency consistency/security | Both `pip check` and locked `pip-audit --strict --no-deps` pass; no known vulnerabilities found |
| Frontend | 34 tests pass, no skips; clean install, production npm audit (0 vulnerabilities), lint, TypeScript, production build pass |
| Packaging | One `finrisk_agent-0.4.1-py3-none-any.whl` and one `finrisk_agent-0.4.1.tar.gz`; clean 3.11/3.12 wheel installs outside checkout both pass API/pipeline/Assurance/certificate smoke |
| StrongTabularReference | Checked-in schema/data/selection/OOF/metrics/hashes and pinned-3.12 replay pass; no canonical refit |
| Historical integrity | E4 public checks pass; E4-S 44/44; E4-R 136/136; no empirical artifact modified |
| E5 | Preflight passes by correctly reporting `BLOCKED / DRAFT_NOT_FROZEN`; freeze chain `NOT_FROZEN` |
| Synthetic/reference checks | Demo fixture and development reference reproduce; updated demo remains explicitly synthetic |
| Links/whitespace | Markdown link checker and `git diff --check` pass |
| Local Docker aggregate gate | **BLOCKED BY HOST ENVIRONMENT**, not passed: Desktop's Linux-engine pipe is absent; official start/restart did not recover it |

The 18 local skips are 12 real-PostgreSQL tests and six deployed-HTTP contract tests.
They must run in the real-stack remote checks. The 84 pytest warnings comprise 32
expected all-missing-feature imputation warnings, 50 upstream scikit-learn `penalty`
deprecations (future compatibility work), and two intentional single-class-fold warnings.
No new filters or suppressions were added. pip-audit recommends full dependency hashes;
npm reports an upstream ESLint support deprecation. These do not conceal test failures.

Security source review found the two upload/numeric-proof issues above and included an
independent boundary investigation and one candidate bypass/regression review. Focused
tests confirm rejection of the original trigger classes and preservation of legitimate
uploads/provenance. This is not a claim of exhaustive line-level security coverage of
every research-statistics, test, data and documentation file, nor a production security
certification. Trusted pickle artifacts remain hash-checked before loading; arbitrary
untrusted serialized models must not be loaded.

## Exact commands

```powershell
$env:FINRISK_LLM_PROVIDER = 'mock'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
.runtime/v041-audit-py312/Scripts/python.exe scripts/verify_v041_release.py `
  --python311 .runtime/v041-audit-py311/Scripts/python.exe `
  --python312 .runtime/v041-audit-py312/Scripts/python.exe `
  --docker-bin 'C:\Users\WSQ\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe' `
  --npm 'C:\Program Files\nodejs\npm.cmd'
```

The command passed all preceding stages and stopped at the first Docker build. Retained
local evidence is in ignored `.runtime/final-release-gate-03.log` and
`.runtime/v041-release-gate/{tests-311.xml,tests-312.xml,coverage-311.json,coverage-312.json}`.
Individual stage commands remain visible in `scripts/verify_v041_release.py`.
`scripts/verify_v041.py` checks research/version/provenance artifacts without retraining;
it is not the complete deployment/release gate.

## Final remote evidence

Normal CI and the final `Container Release` dry-run must be checked job by job on the
exact final commit. Dispatch only with `version=v0.4.1`, `publish=false`. Candidate
image digests must be identical across build, both Compose validations, scans and any
later human-authorized promotion; no rebuild between verification and promotion.

The source-identity-matched job results are retained in GitHub Actions rather than
embedding this document's own future commit hash. Before publication, verify the
release candidate SHA against both the [normal CI runs](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/workflows/ci.yml?query=branch%3Atry-v0.4.1)
and [Container Release runs](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/workflows/container-release.yml?query=branch%3Atry-v0.4.1).
The final audit handoff records their exact run IDs and commit SHA. A successful source
CI run alone is insufficient: both digest-bound Compose checks and all four API/Web
vulnerability/secret scans must pass, while the dry-run publication job must be skipped.

## Research boundary

Original frozen E4 has **674** verified outcomes (235 events). E4-S replication and
StrongTabularReference development have **675** verified companies/observations
(235 events, 440 non-events); these are different historical objects, not inconsistent
counts. Every one of the **2,000** E4-S source companies remains a future E5 exclusion.
Historical E1–E4-R evidence and fitted reference artifacts are byte-unchanged. Development
metrics remain design-exposed retrospective evidence, not unbiased or prospective
validation. Scores and policy remain `UNCALIBRATED`; E5 remains unexecuted/unfrozen.
